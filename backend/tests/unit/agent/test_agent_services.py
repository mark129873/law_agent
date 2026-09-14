"""Agent 服务层单元测试（BE-033）。

全部经脚本化 Fake（打分器/Provider/向量库）验证——不加载真实
rerank 模型、不触碰 Milvus（测试封闭性约束，设计 §51）。
"""

import asyncio

import pytest

from app.agent.services.citation_service import CitationService
from app.agent.services.llm_service import (
    LLMService,
    extract_json_block,
    parse_structured_output,
)
from app.agent.services.milvus_service import MilvusService
from app.agent.services.reranker_service import RerankerService
from app.domain.entities.chunk import DocumentChunk, RetrievedChunk
from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.repositories.vector_store import VectorStore
from app.domain.services.embedding import EmbeddingService
from app.agent.subgraphs.legal_rag.schemas import EvidenceGrade


# ---- 测试替身 ----

class FakeLLM(LLMProvider):
    """脚本化 Provider：chat 依次返回预设输出，记录收到的消息。"""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.received: list[list[ChatMessage]] = []

    @property
    def model_name(self) -> str:
        return "fake-model"

    async def chat(self, messages: list[ChatMessage], params=None) -> str:
        self.received.append(list(messages))
        return self._outputs.pop(0) if self._outputs else ""

    async def stream(self, messages: list[ChatMessage], params=None):
        yield ""
        return


class FakeEmbedding(EmbeddingService):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


class FakeVectorStore(VectorStore):
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[float], int, float]] = []

    async def initialize(self) -> None: ...
    async def close(self) -> None: ...

    async def add_chunks(self, chunks, embeddings) -> list[str]:
        return []

    async def hybrid_search(self, query_text, query_embedding, top_k=4, min_score=0.0):
        self.calls.append((query_text, query_embedding, top_k, min_score))
        chunk = DocumentChunk(document_id="d1", content=f"命中：{query_text}", chunk_id="c1")
        return [RetrievedChunk(chunk=chunk, score=0.9)]

    async def delete_by_document(self, document_id: str) -> int:
        return 0


class FakeScorer:
    """脚本化打分器：按文档顺序返回预设分数，可注入异常。"""

    def __init__(self, scores: list[float] | Exception) -> None:
        self._scores = scores
        self.calls: list[tuple[str, list[str]]] = []

    async def score(self, query: str, documents: list[str]) -> list[float]:
        self.calls.append((query, list(documents)))
        if isinstance(self._scores, Exception):
            raise self._scores
        return list(self._scores)


# ---- extract_json_block / parse_structured_output ----

def test_extract_json_block_plain_and_fenced():
    assert extract_json_block('{"a": 1}') == {"a": 1}
    assert extract_json_block('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_block('说明文字 {"a": {"b": "含}括号"}} 尾部') == {"a": {"b": "含}括号"}}
    assert extract_json_block('["子查询1", "子查询2"]') == ["子查询1", "子查询2"]
    assert extract_json_block("完全不是 JSON") is None
    assert extract_json_block("") is None


def test_parse_structured_output_validates_schema():
    from app.agent.schemas import OrchestratorDecision

    good = '{"action": "local_rag", "reason": "需要知识库"}'
    decision = parse_structured_output(good, OrchestratorDecision)
    assert decision is not None and decision.action == "local_rag"


# ---- LLMService ----

def test_structured_invoke_parses_first_output():
    provider = FakeLLM(['{"sufficient": true, "confidence": 0.9}'])
    service = LLMService(provider)
    default = EvidenceGrade()
    grade = asyncio.run(
        service.structured_invoke([ChatMessage(role=MessageRole.USER, content="q")], EvidenceGrade, default=default)
    )
    assert grade.sufficient is True and grade.confidence == 0.9


def test_structured_invoke_retries_then_succeeds():
    provider = FakeLLM(["不是 JSON", '{"sufficient": false}'])
    service = LLMService(provider)
    grade = asyncio.run(
        service.structured_invoke([], EvidenceGrade, default=EvidenceGrade(sufficient=True))
    )
    # 重试成功 → 用重试结果而非默认
    assert grade.sufficient is False
    assert len(provider.received) == 2
    # 第二次调用附带修正指令
    assert any("JSON" in m.content for m in provider.received[1])


def test_structured_invoke_falls_back_to_safe_default():
    provider = FakeLLM(["坏输出一", "坏输出二"])
    service = LLMService(provider)
    default = EvidenceGrade(sufficient=False, reason="safe")
    grade = asyncio.run(service.structured_invoke([], EvidenceGrade, default=default))
    assert grade.reason == "safe"  # 重试耗尽 → 安全默认
    assert len(provider.received) == 2  # 首次 + 重试 1 次（设计 §47）


def test_invoke_passthrough():
    provider = FakeLLM(["普通回答"])
    service = LLMService(provider)
    assert asyncio.run(service.invoke([ChatMessage(role=MessageRole.USER, content="q")])) == "普通回答"


# ---- MilvusService ----

def test_milvus_service_passes_query_and_vector_to_port():
    embedding, store = FakeEmbedding(), FakeVectorStore()
    service = MilvusService(embedding, store)
    results = asyncio.run(service.hybrid_search("专利期限", top_k=7, min_score=0.1))
    assert store.calls == [("专利期限", [1.0, 0.0], 7, 0.1)]
    assert results[0].chunk.content == "命中：专利期限"


# ---- RerankerService ----

def _docs() -> list[dict]:
    return [
        {"chunk_id": "c1", "content": "低相关"},
        {"chunk_id": "c2", "content": "高相关"},
        {"chunk_id": "c3", "content": "中相关"},
    ]


def test_rerank_orders_by_score_desc_and_truncates():
    service = RerankerService(FakeScorer([0.1, 0.9, 0.5]))
    result = asyncio.run(service.rerank("原始问题", _docs(), top_n=2))
    assert [item["chunk_id"] for item in result.items] == ["c2", "c3"]
    assert result.degraded is False
    assert result.items[0]["rerank_score"] == 0.9
    assert result.items[0]["content"] == "高相关"  # 原字段保留（复制而非原地改）


def test_rerank_degrades_to_rrf_order_on_scorer_error():
    service = RerankerService(FakeScorer(RuntimeError("model not loaded")))
    docs = _docs()
    result = asyncio.run(service.rerank("原始问题", docs, top_n=2))
    assert result.degraded is True
    assert result.disabled is False
    assert "model not loaded" in result.error
    assert [item["chunk_id"] for item in result.items] == ["c1", "c2"]  # 原序（RRF）截断
    assert all("rerank_score" not in item for item in result.items)  # 降级不写 rerank 分
    assert docs[0] == {"chunk_id": "c1", "content": "低相关"}  # 输入未被污染


def test_rerank_empty_documents_skips_scorer():
    scorer = FakeScorer([1.0])
    service = RerankerService(scorer)
    result = asyncio.run(service.rerank("q", [], top_n=3))
    assert result.items == [] and result.degraded is False
    assert scorer.calls == []


def test_rerank_disabled_degrades_to_rrf_order_without_scoring():
    """RERANK_ENABLED=false：整体降级为原序截断（CPU 无 CUDA 部署的可行性开关）。"""
    scorer = FakeScorer([0.9, 0.1])
    service = RerankerService(scorer, enabled=False)
    docs = [{"chunk_id": "c1", "content": "甲"}, {"chunk_id": "c2", "content": "乙"}]
    result = asyncio.run(service.rerank("q", docs, top_n=1))
    assert result.degraded is False
    assert result.disabled is True
    assert "disabled" in result.error
    assert [item["chunk_id"] for item in result.items] == ["c1"]  # 原序截断
    assert scorer.calls == []  # 不触发打分（不加载模型）


def test_rerank_uses_query_for_scoring():
    scorer = FakeScorer([0.0, 0.0, 0.0])
    service = RerankerService(scorer)
    asyncio.run(service.rerank("原始问题", _docs(), top_n=3))
    # 设计约束 18：统一 rerank 的 query 必须是 original_query
    assert scorer.calls[0][0] == "原始问题"


# ---- CitationService ----

def test_citations_numbered_and_deduped():
    service = CitationService()
    evidence = [
        {"chunk_id": "c1", "document_id": "d1", "title": "专利法", "source_name": "专利法.txt",
         "content": "x", "metadata": {"article_number": "第四十二条"}},
        {"chunk_id": "c2", "document_id": "d2", "title": "民法典", "source_name": "民法典.md", "content": "y", "metadata": {}},
        {"chunk_id": "c1", "document_id": "d1", "title": "专利法", "source_name": "专利法.txt", "content": "x", "metadata": {}},
    ]
    citations = service.build_citations(evidence)
    assert [c.citation_id for c in citations] == ["1", "2"]
    assert citations[0].article_number == "第四十二条"
    assert citations[0].chunk_id == "c1"


# ---- 配置默认值 ----

def test_reranker_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # pymilvus import 的 load_dotenv 副作用会把 .env 的值灌进进程环境
    # （Session 027 已记录），默认值断言前先清除（与 test_settings 同模式）
    for key in ("RERANK_ENABLED", "RERANKER_MODEL_PATH", "RERANKER_DEVICE"):
        monkeypatch.delenv(key, raising=False)
    from app.config.settings import Settings

    settings = Settings(_env_file=None)  # 不读 .env，验证纯默认值
    assert settings.rerank_enabled is True  # 默认开启（设计 §32 忠实）
    assert settings.reranker_model_path == "cross-encoder/ms-marco-MiniLM-L-6-v2"
    assert settings.reranker_device == "cpu"
