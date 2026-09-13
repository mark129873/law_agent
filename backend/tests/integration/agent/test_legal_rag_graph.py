"""Local Legal RAG 子图集成测试（BE-035）。

用 Fake 服务（脚本化 LLM / 内存向量库 / 脚本化打分器）构建与生产
同一拓扑的子图，覆盖设计 §50 RAG Integration 场景：
简单查询 / 复杂多变体 / 恢复循环 / 证据不足 / 检索故障，
并经 astream(custom) 验证 plan/sources 事件序列。
"""

import asyncio
import json

from app.agent.services.llm_service import LLMService
from app.agent.services.milvus_service import MilvusService
from app.agent.services.reranker_service import RerankerService
from app.agent.subgraphs.legal_rag.config import LegalRAGConfig
from app.agent.subgraphs.legal_rag.graph import build_legal_rag_graph
from app.domain.entities.chunk import DocumentChunk, RetrievedChunk
from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.repositories.vector_store import VectorStore
from app.domain.services.embedding import EmbeddingService

CONFIG = LegalRAGConfig()

# 各规划器/评估器系统提示的特征片段 → 输出脚本（按调用次序弹出）
PLANNER_MARKER = "检索规划器"
REWRITE_MARKER = "改写器"
SUBQUERY_MARKER = "子查询生成器"
EXPANSION_MARKER = "扩展器"
GRADER_MARKER = "证据评估器"
RECOVERY_MARKER = "恢复规划器"

GRADER_SUFFICIENT = json.dumps(
    {"sufficient": True, "confidence": 0.9, "local_recovery_possible": False,
     "missing_evidence": [], "conflicts": [], "suggested_external_queries": [], "reason": "证据齐全"},
    ensure_ascii=False,
)
GRADER_INSUFFICIENT = json.dumps(
    {"sufficient": False, "confidence": 0.3, "local_recovery_possible": True,
     "missing_evidence": ["赔偿金计算规则"], "conflicts": [],
     "suggested_external_queries": ["外部检索词"], "reason": "缺计算规则"},
    ensure_ascii=False,
)
GRADER_NO_RECOVERY = json.dumps(
    {"sufficient": False, "confidence": 0.1, "local_recovery_possible": False,
     "missing_evidence": ["无法本地补齐"], "conflicts": [], "suggested_external_queries": [], "reason": "库内无"},
    ensure_ascii=False,
)


class PromptScriptedLLM(LLMProvider):
    """按系统提示特征分流输出的脚本化 LLM（fan-out 下输出与调用者解耦）。"""

    def __init__(self, scripts: dict[str, list[str]], default: str = "") -> None:
        self._scripts = {k: list(v) for k, v in scripts.items()}
        self._default = default
        self.call_log: list[str] = []

    @property
    def model_name(self) -> str:
        return "scripted-model"

    async def chat(self, messages: list[ChatMessage], params=None) -> str:
        system = messages[0].content
        for marker, outputs in self._scripts.items():
            if marker in system:
                self.call_log.append(marker)
                return outputs.pop(0) if outputs else ""
        self.call_log.append("default")
        return self._default

    async def stream(self, messages: list[ChatMessage], params=None):
        yield ""
        return


class FakeEmbedding(EmbeddingService):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


class FakeVectorStore(VectorStore):
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
            document_id="doc-1",
            content=f"专利法第四十二条：{query_text} 的相关条文内容",
            chunk_id=f"chunk-{len(self.calls)}",
            metadata={"filename": "专利法.txt", "chunk_index": len(self.calls)},
        )
        return [RetrievedChunk(chunk=chunk, score=0.5)]

    async def delete_by_document(self, document_id: str) -> int:
        return 0


class FakeScorer:
    async def score(self, query: str, documents: list[str]) -> list[float]:
        # 命中内容更长的得分更高（确定性排序）
        return [float(len(doc)) for doc in documents]


def _build_graph(scripts: dict[str, list[str]], store: FakeVectorStore | None = None, default: str = ""):
    provider = PromptScriptedLLM(scripts, default=default)
    vector_store = store or FakeVectorStore()
    graph = build_legal_rag_graph(
        llm=LLMService(provider),
        milvus=MilvusService(FakeEmbedding(), vector_store),
        reranker=RerankerService(FakeScorer()),
        config=CONFIG,
    )
    return graph, provider, vector_store


def _collect_events(graph, input_state: dict) -> tuple[dict, list]:
    """经生产同款事件机制（ContextVar 发射器）捕获事件与最终状态。

    为什么不用 graph.astream(custom)：langgraph 1.2.11 的 stream writer
    在多模式/子图边界上行为不可靠，生产路径已统一为 ContextVar 注入式
    发射器（app/agent/events.py）——测试直接验证生产机制。
    """

    async def _run():
        from app.agent.events import event_emitter_var

        queue: asyncio.Queue = asyncio.Queue()
        token = event_emitter_var.set(queue.put_nowait)
        try:
            final = await graph.ainvoke(input_state)
        finally:
            event_emitter_var.reset(token)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())
        return final, events

    return asyncio.run(_run())


def test_simple_query_original_only_success():
    graph, llm, store = _build_graph({
        PLANNER_MARKER: [json.dumps({"use_original_query": True, "reason": "单一问题"}, ensure_ascii=False)],
        GRADER_MARKER: [GRADER_SUFFICIENT],
    })
    final, events = _collect_events(graph, {"original_query": "发明专利权的保护期限是多长？", "normalized_query": "发明专利权的保护期限"})
    assert final["rag_status"] == "SUCCESS"
    assert len(final["ranked_evidence"]) >= 1
    assert llm.call_log.count(RECOVERY_MARKER) == 0  # 一次成功，无恢复
    # 事件序列：plan（检索策略）先于 sources
    event_types = [e.type for e in events]
    assert event_types.index("plan") < event_types.index("sources")
    assert [q for q in events[[t for t in event_types].index("plan")].sub_queries] == ["发明专利权的保护期限"]


def test_complex_query_all_variants_then_recovery_success():
    graph, llm, store = _build_graph({
        PLANNER_MARKER: [json.dumps(
            {"use_original_query": True, "use_query_rewrite": True, "use_subquery": True,
             "use_query_expansion": True, "reason": "复杂问题"}, ensure_ascii=False)],
        REWRITE_MARKER: [json.dumps({"queries": ["解除劳动合同赔偿金"]}, ensure_ascii=False)],
        SUBQUERY_MARKER: [
            json.dumps({"queries": ["违法解除的认定", "赔偿金如何计算"]}, ensure_ascii=False),
            json.dumps({"queries": ["赔偿金月数上限"]}, ensure_ascii=False),  # 恢复轮换角度拆分
        ],
        EXPANSION_MARKER: [
            json.dumps({"queries": ["经济补偿 最多十二个月"]}, ensure_ascii=False),
            json.dumps({"queries": ["双倍赔偿金 2N"]}, ensure_ascii=False),
        ],
        GRADER_MARKER: [GRADER_INSUFFICIENT, GRADER_SUFFICIENT],
        RECOVERY_MARKER: [json.dumps({"actions": ["subquery", "query_expansion"], "reason": "补计算规则",
                                      "missing_evidence": ["赔偿金计算规则"]}, ensure_ascii=False)],
    })
    final, events = _collect_events(graph, {"original_query": "被开除了能赔多少？", "normalized_query": "违法解除劳动合同的赔偿"})
    assert final["rag_status"] == "SUCCESS"
    # 恢复循环跑过一轮：规划了 2 个恢复动作
    assert llm.call_log.count(RECOVERY_MARKER) == 1
    assert llm.call_log.count(GRADER_MARKER) == 2  # 首轮不足 + 恢复后充分
    # plan 事件两次（首轮 + 恢复轮），第二轮查询不再含首轮已检索文本
    plan_events = [e for e in events if e.type == "plan"]
    assert len(plan_events) == 2
    second_round = set(plan_events[1].sub_queries)
    first_round = set(plan_events[0].sub_queries)
    assert not (first_round & second_round)  # 恢复轮不重复检索已失败查询
    assert final["retry_count"] == 1


def test_evidence_insufficient_exhausts_budget():
    graph, llm, store = _build_graph({
        PLANNER_MARKER: [json.dumps({"use_original_query": True})],
        GRADER_MARKER: [GRADER_INSUFFICIENT, GRADER_INSUFFICIENT, GRADER_INSUFFICIENT],
        RECOVERY_MARKER: [json.dumps({"actions": ["query_expansion"]}, ensure_ascii=False)] * 2,
        EXPANSION_MARKER: [json.dumps({"queries": [f"扩展{i}"]}, ensure_ascii=False) for i in range(2)],
    })
    final, events = _collect_events(graph, {"original_query": "冷门问题", "normalized_query": "冷门问题"})
    assert final["rag_status"] == "LOCAL_EVIDENCE_INSUFFICIENT"
    # max_retries=2：恢复两轮后停止
    assert llm.call_log.count(RECOVERY_MARKER) == 2
    assert final["retry_count"] == 2
    assert final["missing_evidence"] == ["赔偿金计算规则"]
    assert final["suggested_external_queries"] == ["外部检索词"]
    assert final["ranked_evidence"]  # 已有部分证据仍返回（谨慎回答用）


def test_insufficient_without_local_recovery_goes_direct_to_result():
    graph, llm, store = _build_graph({
        PLANNER_MARKER: [json.dumps({"use_original_query": True})],
        GRADER_MARKER: [GRADER_NO_RECOVERY],
    })
    final, _ = _collect_events(graph, {"original_query": "无关问题", "normalized_query": "无关问题"})
    assert final["rag_status"] == "LOCAL_EVIDENCE_INSUFFICIENT"
    assert llm.call_log.count(RECOVERY_MARKER) == 0  # 不可本地恢复 → 不进恢复循环


def test_retrieval_channel_error_returns_retrieval_error():
    graph, llm, store = _build_graph(
        {PLANNER_MARKER: [json.dumps({"use_original_query": True})], GRADER_MARKER: [GRADER_SUFFICIENT]},
        store=FakeVectorStore(error=RuntimeError("milvus down")),
    )
    final, events = _collect_events(graph, {"original_query": "问题", "normalized_query": "问题"})
    assert final["rag_status"] == "RETRIEVAL_ERROR"
    assert not final["ranked_evidence"]
    # 检索故障不推 sources（没有可靠依据可展示）
    assert all(e.type != "sources" for e in events)


def test_rag_trace_accumulates_across_nodes():
    graph, llm, store = _build_graph({
        PLANNER_MARKER: [json.dumps({"use_original_query": True})],
        GRADER_MARKER: [GRADER_SUFFICIENT],
    })
    final, _ = _collect_events(graph, {"original_query": "问题", "normalized_query": "问题"})
    traced_nodes = {entry["node"] for entry in final["rag_trace"]}
    # 每个节点都写 trace（设计 §48）
    assert {
        "retrieval_planner_agent", "strategy_router_node", "hybrid_retriever_node",
        "evidence_ranking_node", "evidence_grader_agent", "rag_result_node",
    } <= traced_nodes
    assert all("duration_ms" in entry for entry in final["rag_trace"])
