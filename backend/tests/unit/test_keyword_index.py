"""BM25 关键词索引单元测试（BE-028）。

覆盖：写入/检索/删除、快照持久化跨实例恢复、幂等 initialize、
无命中与空索引的空结果契约。语料落在 pytest tmp_path，不污染仓库。
"""

import pytest
import pytest_asyncio

from app.domain.entities.chunk import DocumentChunk
from app.infrastructure.keyword_index.bm25 import Bm25KeywordIndex


def _chunk(document_id: str, content: str, index: int = 0) -> DocumentChunk:
    return DocumentChunk(document_id=document_id, content=content, chunk_index=index, metadata={"filename": f"{document_id}.txt"})


@pytest_asyncio.fixture
async def index(tmp_path) -> Bm25KeywordIndex:
    """预置两条法律知识的 BM25 索引。"""
    ki = Bm25KeywordIndex(str(tmp_path / "bm25.json"))
    await ki.initialize()
    await ki.add_chunks(
        [
            _chunk("doc-a", "劳动者违反服务期约定的，应当按照约定向用人单位支付违约金。"),
            _chunk("doc-b", "用人单位依照本法规定解除劳动合同的，应当向劳动者支付经济补偿。", 1),
        ]
    )
    yield ki
    await ki.close()


@pytest.mark.asyncio
async def test_add_assigns_chunk_ids(index: Bm25KeywordIndex) -> None:
    """无 id 的 chunk 写入后应被补上主键（与 ChromaVectorStore 行为一致）。"""
    chunks = index._chunks
    assert all(chunk.chunk_id for chunk in chunks.values())
    assert len(chunks) == 2


@pytest.mark.asyncio
async def test_search_hits_exact_term(index: Bm25KeywordIndex) -> None:
    """精确词面查询应命中包含该词的 chunk，且得分降序。

    注意：两条语料的小语料场景下 BM25Okapi 的 IDF 会归零（得分 0），
    实现按"命中的不同查询词数量"兜底排序，因此这里只断言非负。
    """
    results = await index.search("违约金", top_k=2)
    assert len(results) == 1
    assert "违约金" in results[0].chunk.content
    assert results[0].score >= 0


@pytest.mark.asyncio
async def test_search_no_match_returns_empty(index: Bm25KeywordIndex) -> None:
    """查询词完全不在语料中时应返回空（BM25 的 0 分命中被过滤）。"""
    results = await index.search("量子力学薛定谔方程", top_k=4)
    assert results == []


@pytest.mark.asyncio
async def test_search_empty_index_returns_empty(tmp_path) -> None:
    """空索引（未写入任何语料）检索应返回空而非报错。"""
    ki = Bm25KeywordIndex(str(tmp_path / "empty.json"))
    await ki.initialize()
    try:
        assert await ki.search("任何问题") == []
        assert await ki.delete_by_document("doc-x") == 0
    finally:
        await ki.close()


@pytest.mark.asyncio
async def test_delete_by_document(index: Bm25KeywordIndex) -> None:
    """按文档删除后该文档内容不再被召回，重复删除返回 0。"""
    removed = await index.delete_by_document("doc-a")
    assert removed == 1
    results = await index.search("违约金 服务期", top_k=4)
    assert all(r.chunk.document_id != "doc-a" for r in results)
    # 另一文档不受影响
    assert any("经济补偿" in r.chunk.content for r in await index.search("经济补偿"))
    assert await index.delete_by_document("doc-a") == 0


@pytest.mark.asyncio
async def test_snapshot_persists_across_instances(tmp_path) -> None:
    """语料快照应跨实例恢复：新实例 initialize 后可检索同样内容。"""
    path = str(tmp_path / "persist.json")
    first = Bm25KeywordIndex(path)
    await first.initialize()
    await first.add_chunks([_chunk("doc-1", "发明专利权的期限为二十年。")])
    await first.close()

    second = Bm25KeywordIndex(path)
    await second.initialize()
    try:
        results = await second.search("专利权期限", top_k=2)
        assert len(results) == 1
        assert "二十年" in results[0].chunk.content
        assert results[0].chunk.metadata.get("filename") == "doc-1.txt"
    finally:
        await second.close()


@pytest.mark.asyncio
async def test_initialize_is_idempotent(index: Bm25KeywordIndex) -> None:
    """重复 initialize 不应丢失已有语料（幂等契约）。"""
    await index.initialize()
    await index.initialize()
    results = await index.search("违约金", top_k=4)
    assert len(results) == 1
