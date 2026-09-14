"""Embedding 服务与知识库入库测试。

两类验证：
1. OllamaEmbeddingService 协议行为（MockTransport 注入，不依赖本机服务）。
2. 知识库入库端到端：内存 Fake 向量库 + 确定性测试 embedding，验证
   Pipeline → Embedding → VectorStore 全链路（本机 Ollama 未开启
   --embeddings，真实向量生成待环境就绪后补验，见 feature_list 记录）。
"""

import hashlib

import httpx
import pytest
import pytest_asyncio

from app.application.services.document_pipeline import DocumentParserFactory, DocumentPipeline
from app.application.services.knowledge_service import KnowledgeIngestionService
from app.domain.services.embedding import EmbeddingService
from app.infrastructure.document_parser.text_parser import TextParser
from app.infrastructure.embedding.ollama_embedding import OllamaEmbeddingService
from tests.fakes import InMemoryVectorStore

# ---- 协议级测试 ----


@pytest.mark.asyncio
async def test_ollama_embedding_parses_batch() -> None:
    """批量 embedding 应解析 embeddings 数组且顺序与输入一致。"""

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        payload = json.loads(request.content)
        assert payload["model"] == "test-embed"
        assert payload["input"] == ["第一条", "第二条"]
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0], [0.0, 1.0]]})

    service = OllamaEmbeddingService("http://mock", "test-embed", transport=httpx.MockTransport(handler))
    vectors = await service.embed_documents(["第一条", "第二条"])
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]


@pytest.mark.asyncio
async def test_ollama_embedding_rejects_count_mismatch() -> None:
    """返回向量数量与输入不一致时必须失败，防止错位入库。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0]]})

    service = OllamaEmbeddingService("http://mock", "test-embed", transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="数量不匹配"):
        await service.embed_documents(["第一条", "第二条"])


@pytest.mark.asyncio
async def test_embedding_empty_input_returns_empty() -> None:
    """空输入直接返回空列表，不发起网络请求。"""
    service = OllamaEmbeddingService("http://mock", "test-embed")
    assert await service.embed_documents([]) == []


# ---- 端到端入库测试（内存 Fake 向量库）----


class DeterministicEmbedding(EmbeddingService):
    """确定性测试 embedding：字符 bigram 哈希词袋，语义相近文本向量相近。

    为什么自造向量：本机 Ollama 未开启 --embeddings；
    该 Fake 保证"相同文本向量相同、不同文本向量不同"，
    足以验证入库与检索链路的正确性。
    """

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        for i in range(len(text) - 1):
            bigram = text[i : i + 2]
            digest = hashlib.md5(bigram.encode("utf-8")).digest()
            vector[digest[0] % self._dim] += 1.0
        return vector

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


@pytest_asyncio.fixture
async def ingestion_service(tmp_path) -> KnowledgeIngestionService:
    """内存 Fake 向量库 + 确定性 embedding 的完整入库服务。"""
    pipeline = DocumentPipeline(parser_factory=DocumentParserFactory([TextParser()]))
    store = InMemoryVectorStore()
    await store.initialize()
    service = KnowledgeIngestionService(pipeline, DeterministicEmbedding(), store)
    yield service
    await store.close()


@pytest.mark.asyncio
async def test_ingest_then_retrieve_relevant_chunk(ingestion_service: KnowledgeIngestionService, tmp_path) -> None:
    """核心验收：上传文档后完成解析、分块、向量化与知识库入库，并可检索命中。"""
    content = (
        "劳动合同违约金条款：劳动者违反服务期约定的，应当按照约定向用人单位支付违约金。"
        "劳动报酬规定：工资应当以货币形式按月支付给劳动者本人，不得克扣或者无故拖欠。"
    )
    chunk_ids = await ingestion_service.ingest_document("doc-1", "劳动法问答.txt", content.encode("utf-8"))
    assert len(chunk_ids) >= 1

    # 用与"违约金"相关的查询检索，应命中入库的 chunk 且带来源 metadata
    query_text = "违反服务期约定支付违约金"
    query_vector = await DeterministicEmbedding().embed_query(query_text)
    store = ingestion_service._vector_store
    results = await store.hybrid_search(query_text, query_vector, top_k=3)
    assert len(results) >= 1
    assert results[0].chunk.document_id == "doc-1"
    assert results[0].chunk.metadata["filename"] == "劳动法问答.txt"
    assert "违约金" in results[0].chunk.content


@pytest.mark.asyncio
async def test_ingest_then_delete_document(ingestion_service: KnowledgeIngestionService) -> None:
    """入库后按 document_id 删除，应清空该文档的全部 chunk。"""
    await ingestion_service.ingest_document(
        "doc-2", "民法典.txt", "合同编总则内容：当事人订立合同，应当遵循公平原则。".encode("utf-8")
    )
    store = ingestion_service._vector_store
    deleted = await store.delete_by_document("doc-2")
    assert deleted >= 1
    remaining = await store.hybrid_search("合同", [1.0] * 64, top_k=10)
    assert all(r.chunk.document_id != "doc-2" for r in remaining)
