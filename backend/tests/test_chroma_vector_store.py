"""Chroma 向量数据库实现测试。

为什么用真实 Chroma 测试：BE-007 的验收标准是"文本及其向量能够写入
Chroma，并能够通过查询获取相关文档 chunk"，内存 Fake 无法证明
持久化与 cosine 空间行为，因此使用 tmp 目录下的真实持久化存储。
"""

import pytest
import pytest_asyncio

from app.domain.entities.chunk import DocumentChunk
from app.infrastructure.vector_store.chroma import ChromaVectorStore


@pytest_asyncio.fixture
async def store(tmp_path):
    """每个测试独占一个持久化目录，避免用例间数据串扰。"""
    vector_store = ChromaVectorStore(str(tmp_path / "chroma"))
    await vector_store.initialize()
    yield vector_store
    await vector_store.close()


@pytest.mark.asyncio
async def test_add_and_search_returns_relevant_chunks(store: ChromaVectorStore) -> None:
    """写入后检索：与查询向量最相关的 chunk 排在最前且带来源信息。"""
    chunks = [
        DocumentChunk(
            document_id="doc-1",
            content="劳动合同违约金条款",
            chunk_index=0,
            metadata={"filename": "劳动合同法.txt"},
        ),
        DocumentChunk(document_id="doc-1", content="劳动报酬支付规定", chunk_index=1),
        DocumentChunk(document_id="doc-2", content="民法典合同编总则", chunk_index=0),
    ]
    embeddings = [
        [1.0, 0.0, 0.0],
        [0.9, 0.1, 0.0],
        [0.0, 1.0, 0.0],
    ]
    ids = await store.add_chunks(chunks, embeddings)
    assert len(ids) == 3
    assert all(ids), "写入后必须返回生成的 chunk id"

    results = await store.search([1.0, 0.05, 0.0], top_k=2)
    assert len(results) == 2
    # 与查询向量同向的 doc-1 内容应最相关
    assert results[0].chunk.document_id == "doc-1"
    assert results[0].chunk.content in ("劳动合同违约金条款", "劳动报酬支付规定")
    assert 0.99 < results[0].score <= 1.0  # cosine 空间：score = 1 - distance
    assert results[0].score >= results[1].score
    # metadata 溯源字段应被还原
    assert results[0].chunk.metadata.get("filename") == "劳动合同法.txt"


@pytest.mark.asyncio
async def test_delete_by_document_is_scoped(store: ChromaVectorStore) -> None:
    """按文档删除：doc-1 的 chunk 被删，doc-2 的仍可检索。"""
    chunks = [
        DocumentChunk(document_id="doc-1", content="甲条款", chunk_index=0),
        DocumentChunk(document_id="doc-2", content="乙条款", chunk_index=0),
    ]
    await store.add_chunks(chunks, [[1.0, 0.0], [0.0, 1.0]])

    deleted = await store.delete_by_document("doc-1")
    assert deleted == 1
    remaining = await store.search([1.0, 0.0], top_k=10)
    assert [r.chunk.document_id for r in remaining] == ["doc-2"]
    # 重复删除返回 0，不报错
    assert await store.delete_by_document("doc-1") == 0


@pytest.mark.asyncio
async def test_persists_across_reconnect(tmp_path) -> None:
    """核心持久化验证：重新创建客户端后向量数据仍在。"""
    persist_dir = str(tmp_path / "chroma_persist")

    first = ChromaVectorStore(persist_dir)
    await first.initialize()
    await first.add_chunks(
        [DocumentChunk(document_id="doc-1", content="跨连接向量", chunk_index=0)],
        [[1.0, 0.0]],
    )
    await first.close()

    second = ChromaVectorStore(persist_dir)
    await second.initialize()
    try:
        results = await second.search([1.0, 0.0], top_k=5)
        assert len(results) == 1
        assert results[0].chunk.content == "跨连接向量"
    finally:
        await second.close()


@pytest.mark.asyncio
async def test_initialize_is_idempotent(store: ChromaVectorStore) -> None:
    """重复 initialize 不应报错或丢数据（对应重启场景）。"""
    await store.add_chunks(
        [DocumentChunk(document_id="doc-1", content="幂等数据", chunk_index=0)],
        [[1.0, 0.0]],
    )
    await store.initialize()
    results = await store.search([1.0, 0.0], top_k=5)
    assert len(results) == 1
