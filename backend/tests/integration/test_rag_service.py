"""RAG 检索服务测试。

端到端使用真实 Chroma + 确定性 embedding：证明检索服务在真实
向量库上按语义命中入库内容，且上下文构建带来源标注。
"""

import hashlib

import pytest
import pytest_asyncio

from app.application.services.document_pipeline import DocumentParserFactory, DocumentPipeline
from app.application.services.knowledge_service import KnowledgeIngestionService
from app.application.services.rag_service import RagService
from app.domain.services.embedding import EmbeddingService
from app.infrastructure.document_parser.text_parser import TextParser
from app.infrastructure.vector_store.chroma import ChromaVectorStore


class DeterministicEmbedding(EmbeddingService):
    """字符 bigram 哈希词袋：同文本向量相同，近义查询存在重叠。"""

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
async def rag_service(tmp_path) -> RagService:
    """真实 Chroma + 预置劳动法知识的检索服务。"""
    store = ChromaVectorStore(str(tmp_path / "chroma"))
    await store.initialize()
    embedding = DeterministicEmbedding()
    ingestion = KnowledgeIngestionService(
        DocumentPipeline(parser_factory=DocumentParserFactory([TextParser()])), embedding, store
    )
    await ingestion.ingest_document(
        "doc-1",
        "劳动法问答.txt",
        (
            "劳动合同违约金条款：劳动者违反服务期约定的，应当按照约定向用人单位支付违约金。"
            "经济补偿条款：用人单位依照本法规定解除劳动合同的，应当向劳动者支付经济补偿。"
        ).encode("utf-8"),
    )
    service = RagService(embedding, store)
    yield service
    await store.close()


@pytest.mark.asyncio
async def test_retrieve_returns_relevant_chunks(rag_service: RagService) -> None:
    """查询应命中相关知识 chunk 并携带来源信息。"""
    results = await rag_service.retrieve("违反服务期约定怎么赔偿", top_k=2)
    assert len(results) >= 1
    assert results[0].chunk.metadata.get("filename") == "劳动法问答.txt"
    assert results[0].score >= results[-1].score


@pytest.mark.asyncio
async def test_build_context_includes_source_label(rag_service: RagService) -> None:
    """上下文文本应包含来源文件名标注，供模型回答时引用依据。"""
    context = await rag_service.build_context("经济补偿怎么计算", top_k=2)
    assert "【来源：劳动法问答.txt】" in context
    assert "经济补偿" in context


@pytest.mark.asyncio
async def test_build_context_empty_when_no_hit(tmp_path) -> None:
    """知识库无相关内容时应返回空串，供上层走"信息不足"策略。"""
    store = ChromaVectorStore(str(tmp_path / "empty_chroma"))
    await store.initialize()
    service = RagService(DeterministicEmbedding(), store)
    try:
        context = await service.build_context("任何问题")
        assert context == ""
    finally:
        await store.close()
