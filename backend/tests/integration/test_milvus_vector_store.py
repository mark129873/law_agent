"""真实 Milvus 混合检索集成测试（BE-029）。

验证生产实现在真实 Milvus standalone 上的完整行为：懒建集合、
稠密 + 稀疏 BM25 双通道命中、RRF 融合排序、按文档删除、跨连接持久化。

服务不可达时（未启动 backend/docker-compose.yml）自动跳过——
这是全部自动化测试中唯一依赖外部服务的文件，其余测试保持封闭性。
测试使用独立集合名并在结束时清理，不污染生产集合 law_chunks。
"""

import hashlib
import uuid

import pytest
import pytest_asyncio

from app.domain.entities.chunk import DocumentChunk
from app.infrastructure.vector_store.milvus import MilvusVectorStore

_MILVUS_URI = "http://127.0.0.1:19530"
_COLLECTION = f"law_chunks_test_{uuid.uuid4().hex[:8]}"


class DeterministicEmbedding:
    """字符 bigram 哈希词袋（维度 64，与生产 embedding 无关，只需确定性）。"""

    DIM = 64

    @staticmethod
    def embed(text: str) -> list[float]:
        vector = [0.0] * DeterministicEmbedding.DIM
        for i in range(len(text) - 1):
            digest = hashlib.md5(text[i : i + 2].encode("utf-8")).digest()
            vector[digest[0] % DeterministicEmbedding.DIM] += 1.0
        return vector


def _milvus_available() -> bool:
    """探测 Milvus 服务是否可达（决定是否跳过本文件）。"""
    try:
        from pymilvus import MilvusClient

        MilvusClient(uri=_MILVUS_URI).get_server_version()
        return True
    except Exception:
        return False


# 模块级探测一次：不可达时整文件跳过（收集期即标注，不占用执行时间）
pytestmark = pytest.mark.skipif(
    not _milvus_available(), reason="Milvus 服务不可达（启动 backend/docker-compose.yml 后运行）"
)


@pytest_asyncio.fixture
async def store():
    """独立集合名的真实 Milvus 实现，测试结束删除集合。"""
    store = MilvusVectorStore(_MILVUS_URI, collection_name=_COLLECTION)
    await store.initialize()
    yield store
    client = store._require_client()
    client.drop_collection(_COLLECTION)
    await store.close()


@pytest_asyncio.fixture
async def seeded_store(store: MilvusVectorStore) -> MilvusVectorStore:
    """预置两条法律知识（不同文档）。"""
    await store.add_chunks(
        [
            DocumentChunk(
                document_id="doc-1",
                content="劳动者违反服务期约定的，应当按照约定向用人单位支付违约金。",
                chunk_index=0,
                metadata={"filename": "劳动法.txt"},
            ),
            DocumentChunk(
                document_id="doc-2",
                content="用人单位依照本法规定解除劳动合同的，应当向劳动者支付经济补偿。",
                chunk_index=1,
                metadata={"filename": "劳动法.txt"},
            ),
        ],
        [DeterministicEmbedding.embed("劳动者违反服务期约定的，应当按照约定向用人单位支付违约金。"),
         DeterministicEmbedding.embed("用人单位依照本法规定解除劳动合同的，应当向劳动者支付经济补偿。")],
    )
    return store


@pytest.mark.asyncio
async def test_hybrid_search_hits_semantic_and_keyword(seeded_store: MilvusVectorStore) -> None:
    """混合检索应同时召回语义相关与词面命中的 chunk，且得分降序。"""
    # 查询向量取自 doc-1 原文（稠密通道强命中），查询文本含 doc-2 关键词
    query_vector = DeterministicEmbedding.embed("劳动者违反服务期约定的，应当按照约定向用人单位支付违约金。")
    results = await seeded_store.hybrid_search("经济补偿", query_vector, top_k=4)
    ids = {r.chunk.document_id for r in results}
    assert ids == {"doc-1", "doc-2"}, "稠密与稀疏两路命中都应出现在融合结果中"
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    # RRF 分数量纲（约 1/k 级别，两路同时命中最大约 2/61）与来源元数据应正确回填
    assert all(0 < r.score <= 0.05 for r in results)
    assert results[0].chunk.metadata.get("filename") == "劳动法.txt"
    assert results[0].chunk.chunk_id  # 主键回填


@pytest.mark.asyncio
async def test_keyword_only_query_hits_sparse_channel(seeded_store: MilvusVectorStore) -> None:
    """词面查询应经稀疏 BM25 通道召回目标 chunk（混合检索的词面价值）。"""
    # 查询文本含 doc-2 的关键词；无论稠密通道返回什么，稀疏命中必须出现
    results = await seeded_store.hybrid_search(
        "经济补偿", DeterministicEmbedding.embed("违约金怎么赔"), top_k=4,
    )
    assert len(results) >= 1
    assert any("经济补偿" in r.chunk.content for r in results)


@pytest.mark.asyncio
async def test_min_score_filters_dense_weak_hits(store: MilvusVectorStore) -> None:
    """min_score（服务端 range search）应剔除稠密通道弱命中（BE-016 语义保持）。

    注意 min_score 只作用于稠密通道：若查询文本与内容词面相交，
    稀疏通道仍可召回（混合检索语义）。因此本用例的查询文本与向量
    都与语料无关，两路均不应有命中。
    """
    content = "劳动者违反服务期约定的，应当支付违约金。"
    await store.add_chunks(
        [DocumentChunk(document_id="doc-1", content=content, metadata={"filename": "f.txt"})],
        [DeterministicEmbedding.embed(content)],
    )
    # 阈值 0.99：任何查询的余弦都无法达到；查询文本为无关英文，BM25 无词面命中
    results = await store.hybrid_search(
        "completely unrelated quantum physics", DeterministicEmbedding.embed("completely unrelated"), top_k=4,
        min_score=0.99,
    )
    assert results == []


@pytest.mark.asyncio
async def test_delete_by_document(store: MilvusVectorStore) -> None:
    """按文档删除：计数正确，删除后不再可召回，重复删除返回 0。"""
    content = "发明专利权的期限为二十年。"
    await store.add_chunks(
        [DocumentChunk(document_id="doc-1", content=content, metadata={"filename": "f.txt"})],
        [DeterministicEmbedding.embed(content)],
    )
    assert await store.delete_by_document("doc-1") == 1
    assert await store.delete_by_document("doc-1") == 0
    results = await store.hybrid_search("专利权期限", DeterministicEmbedding.embed("专利权期限"), top_k=4)
    assert results == []


@pytest.mark.asyncio
async def test_persistence_across_reconnect(store: MilvusVectorStore) -> None:
    """数据随 Milvus 持久化：新实例（模拟重启）initialize 后可继续检索。"""
    content = "试用期最长不得超过六个月。"
    await store.add_chunks(
        [DocumentChunk(document_id="doc-1", content=content, metadata={"filename": "f.txt"})],
        [DeterministicEmbedding.embed(content)],
    )
    reopened = MilvusVectorStore(_MILVUS_URI, collection_name=_COLLECTION)
    await reopened.initialize()
    try:
        results = await reopened.hybrid_search("试用期", DeterministicEmbedding.embed("试用期"), top_k=2)
        assert len(results) == 1
        assert "六个月" in results[0].chunk.content
    finally:
        await reopened.close()
