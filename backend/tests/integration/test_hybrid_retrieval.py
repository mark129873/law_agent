"""混合检索集成测试（BE-028）：真实 Chroma + 真实 BM25 索引。

验证双写、双清与融合检索的端到端协作：
入库后两路均可召回同一 chunk（chunk_id 一致）；
删除后两路同时清空；关闭关键词索引时优雅降级为纯向量。
"""

import hashlib

import pytest
import pytest_asyncio

from app.application.services.document_pipeline import DocumentParserFactory, DocumentPipeline
from app.application.services.knowledge_service import KnowledgeIngestionService
from app.application.services.rag_service import RagService
from app.domain.services.embedding import EmbeddingService
from app.infrastructure.document_parser.text_parser import TextParser
from app.infrastructure.keyword_index.bm25 import Bm25KeywordIndex
from app.infrastructure.vector_store.chroma import ChromaVectorStore


class DeterministicEmbedding(EmbeddingService):
    """字符 bigram 哈希词袋：同文本向量相同（与既有测试同一实现）。"""

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        for i in range(len(text) - 1):
            digest = hashlib.md5(text[i : i + 2].encode("utf-8")).digest()
            vector[digest[0] % self._dim] += 1.0
        return vector

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


@pytest_asyncio.fixture
async def hybrid(tmp_path):
    """真实 Chroma + 真实 BM25 的双写入库与混合检索环境。"""
    store = ChromaVectorStore(str(tmp_path / "chroma"))
    await store.initialize()
    keyword_index = Bm25KeywordIndex(str(tmp_path / "bm25.json"))
    await keyword_index.initialize()
    embedding = DeterministicEmbedding()
    ingestion = KnowledgeIngestionService(
        DocumentPipeline(parser_factory=DocumentParserFactory([TextParser()])),
        embedding,
        store,
        keyword_index=keyword_index,
    )
    rag = RagService(embedding, store, keyword_index=keyword_index)
    await ingestion.ingest_document(
        "doc-1",
        "劳动法问答.txt",
        (
            "劳动合同违约金条款：劳动者违反服务期约定的，应当按照约定向用人单位支付违约金。"
            "经济补偿条款：用人单位依照本法规定解除劳动合同的，应当向劳动者支付经济补偿。"
        ).encode("utf-8"),
    )
    yield store, keyword_index, rag
    await keyword_index.close()
    await store.close()


@pytest.mark.asyncio
async def test_dual_write_populates_both_channels(hybrid) -> None:
    """入库双写后，向量通道与关键词通道都能召回内容且 chunk_id 一致。"""
    store, keyword_index, rag = hybrid
    keyword_hits = await keyword_index.search("经济补偿", top_k=4)
    assert len(keyword_hits) >= 1
    vector_hits = await store.search(await DeterministicEmbedding().embed_query("经济补偿"), top_k=4)
    keyword_ids = {r.chunk.chunk_id for r in keyword_hits}
    vector_ids = {r.chunk.chunk_id for r in vector_hits}
    # 同一 chunk 在两路有同一主键：RRF 融合依赖它去重
    assert keyword_ids & vector_ids, "两路检索应能召回同一 chunk"
    assert keyword_hits[0].chunk.metadata.get("filename") == "劳动法问答.txt"


@pytest.mark.asyncio
async def test_hybrid_retrieve_returns_sorted_unique_results(hybrid) -> None:
    """混合检索输出应得分降序、chunk 去重且携带来源。"""
    _, _, rag = hybrid
    results = await rag.retrieve("违反服务期约定怎么赔偿", top_k=4)
    assert len(results) >= 1
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    chunk_ids = [r.chunk.chunk_id for r in results]
    assert len(chunk_ids) == len(set(chunk_ids))
    assert any("服务期" in r.chunk.content for r in results)


@pytest.mark.asyncio
async def test_dual_delete_clears_both_channels(tmp_path) -> None:
    """删除双清后：关键词通道与向量通道都不再召回该文档内容。"""
    store = ChromaVectorStore(str(tmp_path / "chroma"))
    await store.initialize()
    keyword_index = Bm25KeywordIndex(str(tmp_path / "bm25.json"))
    await keyword_index.initialize()
    embedding = DeterministicEmbedding()
    ingestion = KnowledgeIngestionService(
        DocumentPipeline(parser_factory=DocumentParserFactory([TextParser()])),
        embedding,
        store,
        keyword_index=keyword_index,
    )
    rag = RagService(embedding, store, keyword_index=keyword_index)
    try:
        await ingestion.ingest_document("doc-1", "专利法.txt", "发明专利权的期限为二十年。".encode("utf-8"))
        assert await keyword_index.delete_by_document("doc-1") == 1
        assert await store.delete_by_document("doc-1") >= 1

        # 两路分别验证为空
        assert await keyword_index.search("专利权 期限") == []
        assert await store.search(await embedding.embed_query("专利权期限"), top_k=4) == []
        # 混合检索整体无命中 → 上下文为空串（衔接"信息不足"策略）
        assert await rag.build_context("专利权期限是多久") == ""
    finally:
        await keyword_index.close()
        await store.close()


@pytest.mark.asyncio
async def test_pure_vector_fallback_without_keyword_index(tmp_path) -> None:
    """不注入关键词索引时应优雅降级为纯向量检索（回退开关路径）。"""
    store = ChromaVectorStore(str(tmp_path / "chroma"))
    await store.initialize()
    embedding = DeterministicEmbedding()
    ingestion = KnowledgeIngestionService(
        DocumentPipeline(parser_factory=DocumentParserFactory([TextParser()])), embedding, store
    )
    rag = RagService(embedding, store)
    try:
        await ingestion.ingest_document("doc-1", "劳动法问答.txt", "试用期最长不得超过六个月。".encode("utf-8"))
        results = await rag.retrieve("试用期最长多久", top_k=2)
        assert len(results) >= 1
        assert "试用期" in results[0].chunk.content
    finally:
        await store.close()
