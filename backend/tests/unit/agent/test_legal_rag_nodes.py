"""Local Legal RAG 节点单元测试（BE-034）。

全部经脚本化 Fake（LLM Provider / Embedding / 向量库 / 打分器）验证
节点逻辑；plan/sources 事件的发射经 monkeypatch 捕获（图外无流通道）。
"""

import asyncio

import pytest

from app.agent.constants import (
    RAG_STATUS_LOCAL_EVIDENCE_INSUFFICIENT,
    RAG_STATUS_RETRIEVAL_ERROR,
    RAG_STATUS_SUCCESS,
)
from app.agent.services.llm_service import LLMService
from app.agent.services.milvus_service import MilvusService
from app.agent.services.reranker_service import RerankerService
from app.agent.subgraphs.legal_rag import nodes as rag_nodes
from app.agent.subgraphs.legal_rag.config import LegalRAGConfig
from app.agent.subgraphs.legal_rag.nodes import (
    EvidenceGraderAgent,
    EvidenceRankingNode,
    HybridRetrieverNode,
    RagResultNode,
    RecoveryPlannerAgent,
    RetrievalPlannerAgent,
    StrategyRouterNode,
    QueryExpansionAgent,
    QueryRewriteAgent,
    SubqueryGeneratorAgent,
    route_strategies,
)
from app.domain.entities.chunk import DocumentChunk, RetrievedChunk
from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.repositories.vector_store import VectorStore
from app.domain.services.embedding import EmbeddingService

CONFIG = LegalRAGConfig()


class FakeLLM(LLMProvider):
    """脚本化 Provider：chat 依次返回预设输出。"""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)

    @property
    def model_name(self) -> str:
        return "fake-model"

    async def chat(self, messages: list[ChatMessage], params=None) -> str:
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
    """记录检索调用；可注入异常模拟通道故障。"""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[str] = []
        self._error = error

    async def initialize(self) -> None: ...
    async def close(self) -> None: ...

    async def add_chunks(self, chunks, embeddings) -> list[str]:
        return []

    async def hybrid_search(self, query_text, query_embedding, top_k=4, min_score=0.0):
        self.calls.append(query_text)
        if self._error:
            raise self._error
        chunk = DocumentChunk(
            document_id="d1", content=f"内容：{query_text}", chunk_id=f"c-{len(self.calls)}",
            metadata={"filename": "专利法.txt", "chunk_index": len(self.calls)},
        )
        return [RetrievedChunk(chunk=chunk, score=0.5)]

    async def delete_by_document(self, document_id: str) -> int:
        return 0


class FakeScorer:
    def __init__(self, scores: list[float]) -> None:
        self._scores = scores
        self.queries: list[str] = []

    async def score(self, query: str, documents: list[str]) -> list[float]:
        self.queries.append(query)
        return list(self._scores)


def _state(**overrides) -> dict:
    base = {
        "original_query": "违法解除劳动合同怎么赔偿？",
        "normalized_query": "违法解除劳动合同的赔偿标准？",
        "current_plan": {"use_original_query": True},
    }
    base.update(overrides)
    return base


# ---- RetrievalPlannerAgent ----

def test_retrieval_planner_parses_plan():
    agent = RetrievalPlannerAgent(
        LLMService(FakeLLM(['{"use_original_query": true, "use_subquery": true, "target_evidence": ["赔偿标准"], "reason": "复杂"}'])),
        CONFIG,
    )
    result = asyncio.run(agent(_state()))
    plan = result["retrieval_plan"]
    assert plan["use_original_query"] is True and plan["use_subquery"] is True
    assert plan["target_evidence"] == ["赔偿标准"]


def test_retrieval_planner_defaults_to_original_on_garbage():
    agent = RetrievalPlannerAgent(LLMService(FakeLLM(["不是 JSON"])), CONFIG)
    result = asyncio.run(agent(_state()))
    # 设计 §47：Planner 安全默认 = 仅原始问题
    assert result["retrieval_plan"]["use_original_query"] is True
    assert result["retrieval_plan"]["use_subquery"] is False


# ---- StrategyRouterNode / route_strategies ----

def test_strategy_router_normalizes_recovery_plan():
    node = StrategyRouterNode()
    result = asyncio.run(node(_state(recovery_plan={"actions": ["query_rewrite", "query_expansion"], "reason": "补术语"})))
    current = result["current_plan"]
    assert current["is_recovery"] is True
    assert current["use_query_rewrite"] is True and current["use_query_expansion"] is True
    assert current["use_original_query"] is False  # 恢复轮不重复检索原始问题
    assert current["use_subquery"] is False


def test_strategy_router_first_round_uses_retrieval_plan():
    node = StrategyRouterNode()
    result = asyncio.run(node(_state(retrieval_plan={"use_original_query": True, "use_subquery": True})))
    current = result["current_plan"]
    assert current["is_recovery"] is False and current["use_subquery"] is True


def test_route_strategies_fan_out_and_fallback():
    assert route_strategies({"current_plan": {"use_query_rewrite": True, "use_subquery": True}}) == [
        "query_rewrite_agent", "subquery_generator_agent",
    ]
    # 无变体启用（或空计划）→ 直接进混合检索
    assert route_strategies({"current_plan": {"use_original_query": True}}) == ["hybrid_retriever_node"]
    assert route_strategies({}) == ["hybrid_retriever_node"]


# ---- 查询变体三节点 ----

@pytest.mark.parametrize(
    ("agent_cls", "state_key", "cap"),
    [(QueryRewriteAgent, "rewritten_queries", 2),
     (SubqueryGeneratorAgent, "sub_queries", 5),
     (QueryExpansionAgent, "expanded_queries", 3)],
)
def test_query_variant_agents_parse_cap_and_fallback(agent_cls, state_key, cap):
    # 超量输出被截断到上限
    overflowing = {"queries": [f"变体{i}" for i in range(cap + 3)]}
    agent = agent_cls(LLMService(FakeLLM([__import__("json").dumps(overflowing)])), CONFIG)
    result = asyncio.run(agent(_state()))
    assert len(result[state_key]) == cap
    # 解析失败 → 空列表（原始查询仍在检索队列，流程不中断）
    agent_bad = agent_cls(LLMService(FakeLLM(["不是 JSON"])), CONFIG)
    result_bad = asyncio.run(agent_bad(_state()))
    assert result_bad[state_key] == []


# ---- HybridRetrieverNode ----

def test_hybrid_retriever_assembles_queries_from_variants():
    store = FakeVectorStore()
    node = HybridRetrieverNode(MilvusService(FakeEmbedding(), store), CONFIG)
    state = _state(
        rewritten_queries=["改写查询"],
        sub_queries=["子问题一", "子问题二"],
        expanded_queries=["扩展术语"],
    )
    captured = []
    monkey_target = rag_nodes.hybrid_retriever_node
    original_emit = monkey_target.emit_event
    monkey_target.emit_event = lambda event: captured.append(event)  # type: ignore[assignment]
    try:
        result = asyncio.run(node(state))
    finally:
        monkey_target.emit_event = original_emit
    # 原始问题 + 4 个变体，全部进同一混合检索（约束 16）
    assert len(store.calls) == 5
    assert set(store.calls) == {"违法解除劳动合同的赔偿标准？", "改写查询", "子问题一", "子问题二", "扩展术语"}
    # plan 事件携带全部查询（D1 检索策略展示）
    assert captured and captured[0].type == "plan"
    assert len(captured[0].sub_queries) == 5
    assert result["retrieved_query_texts"] == [q["query"] for q in result["retrieval_queries"]]


def test_hybrid_retriever_excludes_already_retrieved_and_caps():
    store = FakeVectorStore()
    node = HybridRetrieverNode(MilvusService(FakeEmbedding(), store), CONFIG)
    state = _state(
        rewritten_queries=["已检索过", "新查询"],
        sub_queries=[f"子问题{i}" for i in range(10)],
        retrieved_query_texts=["已检索过"],
        current_plan={"use_original_query": False},  # 恢复轮：不再检索原始问题
    )
    result = asyncio.run(node(state))
    queries = result["retrieval_queries"]
    assert "已检索过" not in [q["query"] for q in queries]
    assert all(q["query_type"] != "original" for q in queries)
    assert len(queries) <= CONFIG.max_retrieval_queries


def test_hybrid_retriever_all_queries_failed_sets_retrieval_error():
    node = HybridRetrieverNode(MilvusService(FakeEmbedding(), FakeVectorStore(error=RuntimeError("milvus down"))), CONFIG)
    result = asyncio.run(node(_state()))
    assert "retrieval_error" in result  # 全部失败（各重试 1 次）→ 通道故障（设计 §47）
    assert result["retrieval_candidates"] == []


def test_hybrid_retriever_partial_failure_is_not_error():
    class FlakyStore(FakeVectorStore):
        async def hybrid_search(self, query_text, query_embedding, top_k=4, min_score=0.0):
            if "坏查询" in query_text:
                raise RuntimeError("boom")
            return await super().hybrid_search(query_text, query_embedding, top_k, min_score)

    node = HybridRetrieverNode(MilvusService(FakeEmbedding(), FlakyStore()), CONFIG)
    state = _state(rewritten_queries=["坏查询"])
    result = asyncio.run(node(state))
    assert "retrieval_error" not in result  # 部分成功不算通道故障
    assert result["retrieval_candidates"]  # 好查询的候选保留


# ---- EvidenceRankingNode ----

def test_evidence_ranking_pre_truncates_candidates_by_rrf_before_rerank():
    """粗排→精排：超过 rerank_max_candidates 的候选按 RRF 分预截断（ADR-0004 补充）。"""
    class CountingScorer:
        def __init__(self) -> None:
            self.docs_seen: list[str] = []

        async def score(self, query: str, documents: list[str]) -> list[float]:
            self.docs_seen = list(documents)
            return [float(len(doc)) for doc in documents]

    scorer = CountingScorer()
    node = EvidenceRankingNode(RerankerService(scorer), CONFIG)
    # 构造 30 个去重后的候选：rrf_score 从 0.30 递减到 0.01
    candidates = [
        {"chunk_id": f"c{i}", "content": f"内容{i}", "rrf_score": 0.3 - i * 0.01}
        for i in range(30)
    ]
    result = asyncio.run(node(_state(retrieval_candidates=candidates)))
    # 只有 RRF 前 20 进入 rerank（配置默认 rerank_max_candidates=20）
    assert len(scorer.docs_seen) == CONFIG.rerank_max_candidates
    # 预截断保留的是 RRF 高分档（c0..c19），低分档不占精排预算
    assert scorer.docs_seen[0] == "内容0"
    trace = result["rag_trace"][0]
    assert trace["input_count"] == 30 and trace["pre_rerank_count"] == 20
    assert len(result["ranked_evidence"]) <= CONFIG.rerank_top_k


def test_evidence_ranking_dedups_and_reranks_with_original_query():
    scorer = FakeScorer([0.1, 0.9])
    node = EvidenceRankingNode(RerankerService(scorer), CONFIG)
    candidates = [
        {"chunk_id": "c1", "content": "甲", "query": "问题一", "rrf_score": 0.02},
        {"chunk_id": "c1", "content": "甲", "query": "问题二", "rrf_score": 0.03},  # 重复命中
        {"chunk_id": "c2", "content": "乙", "query": "问题二", "rrf_score": 0.01},
    ]
    result = asyncio.run(node(_state(retrieval_candidates=candidates)))
    assert len(result["ranked_evidence"]) == 2
    assert result["ranked_evidence"][0]["chunk_id"] == "c2"  # rerank 高分在前
    assert result["ranked_evidence"][0]["rerank_score"] == 0.9
    assert scorer.queries == ["违法解除劳动合同的赔偿标准？"]  # 约束 18：original_query 重排
    trace = result["rag_trace"][0]
    assert trace["input_count"] == 3 and trace["dedup_count"] == 2 and trace["reranker_degraded"] is False


# ---- EvidenceGraderAgent ----

def test_evidence_grader_parses_grade():
    raw = ('{"sufficient": true, "confidence": 0.9, "local_recovery_possible": false, '
           '"missing_evidence": [], "conflicts": [], "suggested_external_queries": [], "reason": "齐了"}')
    agent = EvidenceGraderAgent(LLMService(FakeLLM([raw])), CONFIG)
    result = asyncio.run(agent(_state(ranked_evidence=[{"chunk_id": "c1", "content": "x", "source_name": "法"}])))
    assert result["evidence_sufficient"] is True
    assert result["evidence_confidence"] == 0.9


def test_evidence_grader_defaults_to_insufficient():
    agent = EvidenceGraderAgent(LLMService(FakeLLM(["坏输出"])), CONFIG)
    result = asyncio.run(agent(_state(retry_count=0)))
    # 设计 §47：Grader 安全默认 = 不充分（宁可多检索不可误判充分）
    assert result["evidence_sufficient"] is False
    assert result["local_recovery_possible"] is True  # 预算内默认允许恢复


# ---- RecoveryPlannerAgent ----

def test_recovery_planner_parses_and_increments_retry():
    raw = '{"actions": ["subquery"], "reason": "拆细", "missing_evidence": ["计算规则"]}'
    agent = RecoveryPlannerAgent(LLMService(FakeLLM([raw])), CONFIG)
    result = asyncio.run(agent(_state(retry_count=0, missing_evidence=["计算规则"])))
    assert result["retry_count"] == 1
    assert result["recovery_plan"]["actions"] == ["subquery"]


def test_recovery_planner_default_avoids_executed_strategies():
    agent = RecoveryPlannerAgent(LLMService(FakeLLM(["坏输出"])), CONFIG)
    state = _state(rewritten_queries=["已用改写"], sub_queries=["已用拆分"])
    result = asyncio.run(agent(state))
    # 安全默认：改写/拆分都执行过 → 默认扩展
    assert result["recovery_plan"]["actions"] == ["query_expansion"]


# ---- RagResultNode ----

@pytest.mark.parametrize(
    ("state_overrides", "expected_status"),
    [
        ({"evidence_sufficient": True}, RAG_STATUS_SUCCESS),
        ({"evidence_sufficient": False}, RAG_STATUS_LOCAL_EVIDENCE_INSUFFICIENT),
        ({"retrieval_error": "boom", "evidence_sufficient": True}, RAG_STATUS_RETRIEVAL_ERROR),
    ],
)
def test_rag_result_status_decision(state_overrides, expected_status):
    node = RagResultNode()
    result = asyncio.run(node(_state(ranked_evidence=[{"source_name": "法", "content": "条"}], **state_overrides)))
    assert result["rag_status"] == expected_status


def test_rag_result_emits_sources_only_with_evidence():
    node = RagResultNode()
    captured: list = []
    module = rag_nodes.rag_result_node
    original = module.emit_event
    module.emit_event = lambda event: captured.append(event)  # type: ignore[assignment]
    try:
        asyncio.run(node(_state(ranked_evidence=[{"source_name": "专利法.txt", "content": "第二条"}], evidence_sufficient=True)))
        asyncio.run(node(_state(ranked_evidence=[], evidence_sufficient=False)))
        asyncio.run(node(_state(ranked_evidence=[], evidence_sufficient=False, retrieval_error="x")))
    finally:
        module.emit_event = original
    # 有证据 → 推 sources（先于 delta 契约）；无证据与检索故障 → 不推
    assert len(captured) == 1
    assert captured[0].type == "sources"
    assert captured[0].sources == ({"source": "专利法.txt", "content": "第二条"},)
