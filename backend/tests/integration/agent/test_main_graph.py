"""主图端到端集成测试（BE-041/BE-039，设计 §50 Main Graph E2E）。

用 Fake 服务构建与生产完全一致的主图（含 legal_rag 子图），覆盖：
简单法律问题（RAG 成功）/ 一般性对话（直接回答）/ 本地无证据（信息不足）
/ Web 请求（DISABLED）/ Plugin 请求（NOT_IMPLEMENTED），
并验证 BE-041 状态事件跨子图贯通与事件顺序契约。
"""

import asyncio
import json

from app.agent import create_qa_workflow
from app.agent.config import AgentConfig
from app.agent.events import event_emitter_var
from app.agent.services.reranker_service import RerankerService
from app.agent.subgraphs.legal_rag.config import LegalRAGConfig
from app.domain.entities.chunk import DocumentChunk, RetrievedChunk
from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.repositories.vector_store import VectorStore
from app.domain.services.embedding import EmbeddingService

# 各 LLM 节点系统提示的特征片段
ROUTER_MARKER = "意图路由器"
ORCHESTRATOR_MARKER = "顶层编排器"
PLANNER_MARKER = "检索规划器"
GRADER_MARKER = "证据评估器"
JUDGE_MARKER = "回答校验器"

GRADER_SUFFICIENT = json.dumps(
    {"sufficient": True, "confidence": 0.9, "local_recovery_possible": False,
     "missing_evidence": [], "conflicts": [], "suggested_external_queries": [], "reason": "证据齐全"},
    ensure_ascii=False,
)
GRADER_NO_RECOVERY = json.dumps(
    {"sufficient": False, "confidence": 0.1, "local_recovery_possible": False,
     "missing_evidence": ["冷门主题"], "conflicts": [], "suggested_external_queries": [], "reason": "库内无"},
    ensure_ascii=False,
)
ANSWER_WITH_SOURCE = "发明专利权的期限为二十年。【来源：专利法.txt】"
ANSWER_INSUFFICIENT = "知识库中暂无相关依据，建议咨询专业律师。"
ANSWER_GENERAL = "你好！我是法律知识库助手，很高兴为你服务。"


class MarkerFakeLLM(LLMProvider):
    """按系统提示特征分流的 Fake LLM：chat 弹脚本，stream 产出 answer 文本。"""

    def __init__(self, scripts: dict[str, list[str]], answer: str = ANSWER_INSUFFICIENT) -> None:
        self._scripts = {k: list(v) for k, v in scripts.items()}
        self._answer = answer
        self.call_log: list[str] = []

    @property
    def model_name(self) -> str:
        return "fake-model"

    def _take(self, system: str) -> str:
        for marker, outputs in self._scripts.items():
            if marker in system:
                self.call_log.append(marker)
                return outputs.pop(0) if outputs else ""
        self.call_log.append("default")
        return ""

    async def chat(self, messages: list[ChatMessage], params=None) -> str:
        return self._take(messages[0].content)

    async def stream(self, messages: list[ChatMessage], params=None):
        self._take(messages[0].content)  # 记录生成调用（生成节点不消费脚本）
        for i in range(0, len(self._answer), 6):
            yield self._answer[i : i + 6]


class FakeEmbedding(EmbeddingService):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t)), 1.0] for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 1.0]


class FakeVectorStore(VectorStore):
    def __init__(self, with_document: bool = True) -> None:
        self._with_document = with_document

    async def initialize(self) -> None: ...
    async def close(self) -> None: ...

    async def add_chunks(self, chunks, embeddings) -> list[str]:
        return []

    async def hybrid_search(self, query_text, query_embedding, top_k=4, min_score=0.0):
        if not self._with_document:
            return []
        chunk = DocumentChunk(
            document_id="doc-1",
            content="发明专利权的期限为二十年，自申请日起计算。",
            chunk_id="chunk-1",
            metadata={"filename": "专利法.txt", "chunk_index": 0},
        )
        return [RetrievedChunk(chunk=chunk, score=0.6)]

    async def delete_by_document(self, document_id: str) -> int:
        return 0


class FakeScorer:
    async def score(self, query: str, documents: list[str]) -> list[float]:
        return [float(len(doc)) for doc in documents]


def _build_workflow(scripts: dict[str, list[str]], answer: str = ANSWER_INSUFFICIENT, with_document: bool = True):
    llm = MarkerFakeLLM(scripts, answer=answer)
    workflow = create_qa_workflow(
        llm,
        embedding=FakeEmbedding(),
        vector_store=FakeVectorStore(with_document=with_document),
        reranker=RerankerService(FakeScorer()),
        agent_config=AgentConfig(),
        rag_config=LegalRAGConfig(),
    )
    return workflow, llm


def _run(workflow, question: str) -> tuple[dict, list]:
    """ainvoke 执行 + ContextVar 捕获事件（生产同款事件机制）。"""

    async def _run():
        captured: list = []
        token = event_emitter_var.set(captured.append)
        try:
            final = await workflow.ainvoke({"question": question, "history": []})
        finally:
            event_emitter_var.reset(token)
        return final, captured

    return asyncio.run(_run())


def test_case1_legal_question_rag_success():
    """Case 1：法律事实问题 → Local RAG → SUCCESS → 回答（事件序 plan→sources→delta）。"""
    workflow, llm = _build_workflow(
        {
            ORCHESTRATOR_MARKER: ['{"action": "local_rag"}', '{"action": "finish"}'],
            PLANNER_MARKER: [json.dumps({"use_original_query": True})],
            GRADER_MARKER: [GRADER_SUFFICIENT],
        },
        answer=ANSWER_WITH_SOURCE,
    )
    final, events = _run(workflow, "发明专利权的保护期限是多长？")
    # 最终状态与端口输出键
    assert final["rag_status"] == "SUCCESS"
    assert final["answer"] == ANSWER_WITH_SOURCE
    assert final["citations"] and final["citations"][0]["citation_id"] == "1"
    # 事件顺序契约：plan → sources → delta（过滤 status/think 过程事件后，BE-042）
    business = [e for e in events if e.type not in ("status", "think")]
    types = [e.type for e in business]
    assert types.index("plan") < types.index("sources") < types.index("delta")
    # BE-041：状态事件覆盖主图与子图节点（ContextVar 跨子图贯通）
    status_nodes = {e.node for e in events if e.type == "status"}
    assert "query_router_agent" in status_nodes  # 主图节点
    assert {"hybrid_retriever_node", "evidence_ranking_node", "rag_result_node"} <= status_nodes  # 子图节点
    assert all(e.label for e in events if e.type == "status")  # 中文标签必有
    # BE-042：思考内容事件（决策输出/运行细节）随节点流转产出，契约字段齐全
    think_events = [e for e in events if e.type == "think"]
    assert think_events, "RAG 路径应产生 think 事件"
    assert all(e.label and e.text and len(e.text) <= 121 for e in think_events)  # text ≤120 字契约
    think_nodes = {e.node for e in think_events}
    assert {"query_router_agent", "orchestrator_agent", "evidence_grader_agent"} <= think_nodes


def test_case2_general_question_direct_answer():
    """Case 2：一般性对话 → 直接回答（不检索：无 plan/sources）。"""
    workflow, llm = _build_workflow(
        {
            ROUTER_MARKER: [json.dumps({"normalized_query": "你好", "intent": "general_question",
                                        "request_type": "direct"}, ensure_ascii=False)],
            ORCHESTRATOR_MARKER: ['{"action": "direct_answer"}', '{"action": "finish"}'],
        },
        answer=ANSWER_GENERAL,
    )
    final, events = _run(workflow, "你好，你是谁？")
    assert final["answer"] == ANSWER_GENERAL
    assert final["last_capability"] == "direct_answer"
    business = [e for e in events if e.type not in ("status", "think")]
    assert all(e.type != "plan" and e.type != "sources" for e in business)  # 未检索
    assert any(e.type == "delta" for e in business)
    assert llm.call_log.count(PLANNER_MARKER) == 0  # 路由直达，不经检索规划


def test_case3_no_evidence_declares_insufficient():
    """Case 3：本地无相关证据 → LOCAL_EVIDENCE_INSUFFICIENT → 信息不足声明。"""
    workflow, llm = _build_workflow(
        {
            ORCHESTRATOR_MARKER: ['{"action": "local_rag"}', '{"action": "finish"}'],
            PLANNER_MARKER: [json.dumps({"use_original_query": True})],
            GRADER_MARKER: [GRADER_NO_RECOVERY],
        },
        answer=ANSWER_INSUFFICIENT,
        with_document=False,
    )
    final, events = _run(workflow, "完全不相关的冷门问题？")
    assert final["rag_status"] == "LOCAL_EVIDENCE_INSUFFICIENT"
    assert final["answer"] == ANSWER_INSUFFICIENT  # BE-017 契约声明
    assert all(e.type != "sources" for e in events if e.type not in ("status", "think"))  # 无命中无来源事件
    assert final["missing_evidence"] == ["冷门主题"]


def test_case4_web_request_disabled():
    """Case 4：Web 请求（开关默认关）→ DISABLED → 说明性回答。"""
    workflow, llm = _build_workflow(
        {
            ROUTER_MARKER: [json.dumps({"normalized_query": "搜最新法规", "intent": "web_request",
                                        "request_type": "web"}, ensure_ascii=False)],
            ORCHESTRATOR_MARKER: ['{"action": "web_search"}', '{"action": "finish"}'],
        },
        answer="网络搜索功能尚未开通，您可以直接提出法律问题。",
    )
    final, events = _run(workflow, "帮我上网搜一下最新法规")
    assert final["last_capability"] == "web_search"
    assert final["capability_status"] == "DISABLED"
    assert "尚未开通" in final["answer"]
    assert all(e.type != "sources" for e in events if e.type not in ("status", "think"))


def test_case5_plugin_request_not_implemented():
    """Case 5：Plugin 请求 → NOT_IMPLEMENTED → 说明性回答。"""
    workflow, llm = _build_workflow(
        {
            ROUTER_MARKER: [json.dumps({"normalized_query": "用计算器", "intent": "plugin_request",
                                        "request_type": "plugin"}, ensure_ascii=False)],
            ORCHESTRATOR_MARKER: ['{"action": "plugin"}', '{"action": "finish"}'],
        },
        answer="插件能力尚未开通。",
    )
    final, _ = _run(workflow, "帮我用日历插件安排日程")
    assert final["last_capability"] == "plugin"
    assert final["capability_status"] == "NOT_IMPLEMENTED"
    assert "尚未开通" in final["answer"]


def test_adapter_astream_yields_events_in_order():
    """适配器 astream（生产流式路径）：事件按执行顺序产出且含子图事件。"""
    workflow, _ = _build_workflow(
        {
            ORCHESTRATOR_MARKER: ['{"action": "local_rag"}', '{"action": "finish"}'],
            PLANNER_MARKER: [json.dumps({"use_original_query": True})],
            GRADER_MARKER: [GRADER_SUFFICIENT],
        },
        answer=ANSWER_WITH_SOURCE,
    )

    async def _consume():
        return [event async for event in workflow.astream({"question": "发明专利权的保护期限？", "history": []})]

    events = asyncio.run(_consume())
    types = [e.type for e in events]
    assert "status" in types and "plan" in types and "delta" in types
    business = [e for e in events if e.type != "status"]
    b_types = [e.type for e in business]
    assert b_types.index("plan") < b_types.index("sources") < b_types.index("delta")
