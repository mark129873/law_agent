"""主图节点单元测试（BE-036）。

脚本化 Fake 覆盖：路由解析与安全默认、编排预算双保险、观察归一、
直接回答流式与打回、回答生成四情形、grounding 双规则与跳过、
兜底与收尾节点。
"""

import asyncio
import json

import pytest

from app.agent.config import AgentConfig
from app.agent.constants import (
    CAPABILITY_DISABLED,
    CAPABILITY_LOCAL_EVIDENCE_INSUFFICIENT,
    CAPABILITY_NOT_IMPLEMENTED,
    CAPABILITY_SUCCESS,
    RAG_STATUS_SUCCESS,
)
from app.agent.nodes import (
    AnswerGeneratorAgent,
    DirectAnswerAgent,
    FallbackGeneratorAgent,
    FinalAnswerNode,
    GroundingCheckerAgent,
    ObservationNode,
    OrchestratorAgent,
    QueryRouterAgent,
    ActionRouterNode,
    route_action,
)
from app.agent.services.citation_service import CitationService
from app.agent.services.llm_service import LLMService
from app.agent.state import AgentState
from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole
from app.domain.repositories.llm_provider import LLMProvider


class StreamingFakeLLM(LLMProvider):
    """chat 弹预设输出；stream 逐段产出预设文本并记录。"""

    def __init__(self, chat_outputs: list[str] | None = None, stream_text: str = "测试回答内容") -> None:
        self._chat_outputs = list(chat_outputs or [])
        self._stream_text = stream_text
        self.streamed: list[list[ChatMessage]] = []

    @property
    def model_name(self) -> str:
        return "fake-model"

    async def chat(self, messages: list[ChatMessage], params=None) -> str:
        return self._chat_outputs.pop(0) if self._chat_outputs else ""

    async def stream(self, messages: list[ChatMessage], params=None):
        self.streamed.append(list(messages))
        for i in range(0, len(self._stream_text), 4):
            yield self._stream_text[i : i + 4]


CONFIG = AgentConfig()


def _state(**overrides) -> AgentState:
    base: AgentState = {"question": "你好，你是谁？"}
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


def _events_of(monkeypatch: pytest.MonkeyPatch, module) -> list:
    """替换模块级 emit_event 捕获事件（图外无流通道）。"""
    captured: list = []
    monkeypatch.setattr(module, "emit_event", lambda event: captured.append(event))
    return captured


# ---- QueryRouterAgent ----

def test_query_router_parses_and_defaults():
    raw = json.dumps({"normalized_query": "违法解除劳动合同的赔偿标准",
                      "intent": "legal_question", "request_type": "local_rag",
                      "extracted_conditions": {"年限": "7年"}}, ensure_ascii=False)
    result = asyncio.run(QueryRouterAgent(LLMService(StreamingFakeLLM([raw])), CONFIG)(_state(question="被开除了怎么赔")))
    assert result["request_type"] == "local_rag"
    assert result["extracted_conditions"] == {"年限": "7年"}
    assert result["web_search_enabled"] is False  # 配置默认（一期 Stub）

    # 解析失败 → 原问题透传 + legal_question 默认（宁可多检索）
    result_bad = asyncio.run(QueryRouterAgent(LLMService(StreamingFakeLLM(["坏输出"])), CONFIG)(
        _state(question="原样问题")))
    assert result_bad["normalized_query"] == "原样问题"
    assert result_bad["request_type"] == "local_rag"


# ---- OrchestratorAgent / ActionRouterNode ----

def test_orchestrator_parses_decision_and_forces_finish_on_budget():
    raw = json.dumps({"action": "direct_answer", "reason": "闲聊"}, ensure_ascii=False)
    result = asyncio.run(OrchestratorAgent(LLMService(StreamingFakeLLM([raw])), CONFIG)(
        _state(global_step_count=0)))
    assert result["current_action"] == "direct_answer"

    # 预算耗尽：不调 LLM（无 chat 输出）强制 finish
    forced = asyncio.run(OrchestratorAgent(LLMService(StreamingFakeLLM([])), CONFIG)(
        _state(global_step_count=CONFIG.max_global_steps)))
    assert forced["current_action"] == "finish"
    assert "预算耗尽" in forced["action_reason"]


def test_route_action_mapping():
    node = ActionRouterNode()
    asyncio.run(node(_state(current_action="local_rag")))
    assert route_action({"current_action": "local_rag"}) == "legal_rag_subgraph"
    assert route_action({"current_action": "web_search"}) == "web_search_entry_node"
    assert route_action({"current_action": "finish"}) == "answer_generator_agent"
    assert route_action({}) == "answer_generator_agent"  # 缺省安全收尾


# ---- ObservationNode ----

def test_observation_normalizes_rag_result_and_counts_step():
    result = asyncio.run(ObservationNode()(_state(
        last_capability="local_rag",
        rag_status=RAG_STATUS_SUCCESS,
        ranked_evidence=[{"chunk_id": "c1", "content": "条文", "source_name": "专利法.txt"}],
        missing_evidence=[],
        suggested_external_queries=[],
        global_step_count=1,
    )))
    assert result["capability_status"] == CAPABILITY_SUCCESS
    assert result["last_capability"] == "local_legal_rag"
    assert result["evidence"][0]["chunk_id"] == "c1"
    assert result["global_step_count"] == 2


def test_observation_passthrough_stub_result():
    result = asyncio.run(ObservationNode()(_state(
        last_capability="web_search",
        capability_result={"capability": "web_search", "status": CAPABILITY_NOT_IMPLEMENTED,
                           "evidence": [], "citations": [], "metadata": {}},
        global_step_count=0,
    )))
    assert result["capability_status"] == CAPABILITY_NOT_IMPLEMENTED
    assert result["evidence"] == []


# ---- DirectAnswerAgent ----

def test_direct_answer_streams_and_sets_capability(monkeypatch: pytest.MonkeyPatch):
    events = _events_of(monkeypatch, __import__("app.agent.nodes.direct_answer_agent", fromlist=["x"]))
    llm = StreamingFakeLLM(stream_text="你好！我是法律助手")
    result = asyncio.run(DirectAnswerAgent(LLMService(llm))(_state()))
    deltas = [e for e in events if e.type == "delta"]
    assert deltas  # 直接回答路径流式输出
    assert result["capability_result"]["capability"] == "direct_answer"
    assert result["answer_draft"] == "你好！我是法律助手"


def test_direct_answer_emits_regenerating_on_retry(monkeypatch: pytest.MonkeyPatch):
    events = _events_of(monkeypatch, __import__("app.agent.nodes.direct_answer_agent", fromlist=["x"]))
    asyncio.run(DirectAnswerAgent(LLMService(StreamingFakeLLM()))(_state(answer_draft="旧回答")))
    assert events[0].type == "regenerating"  # 打回重答先通知前端清空


# ---- AnswerGeneratorAgent ----

def test_answer_generator_passthrough_direct_draft():
    result = asyncio.run(AnswerGeneratorAgent(LLMService(StreamingFakeLLM(stream_text="不应被调用")))(
        _state(capability_result={"capability": "direct_answer", "status": CAPABILITY_SUCCESS,
                                  "content": "直接回答", "evidence": [], "citations": [], "metadata": {}})))
    assert result["answer_draft"] == "直接回答"  # 透传，不再调模型


def test_answer_generator_rag_path_streams_with_context(monkeypatch: pytest.MonkeyPatch):
    events = _events_of(monkeypatch, __import__("app.agent.nodes.answer_generator_agent", fromlist=["x"]))
    llm = StreamingFakeLLM(stream_text="依据第四十二条回答")
    result = asyncio.run(AnswerGeneratorAgent(LLMService(llm))(_state(
        original_query="专利期限",
        capability_result={"capability": "local_legal_rag", "status": CAPABILITY_SUCCESS,
                           "evidence": [{"source_name": "专利法.txt", "content": "期限二十年"}], "citations": [], "metadata": {}},
        evidence=[{"source_name": "专利法.txt", "content": "期限二十年"}],
    )))
    assert result["answer_draft"] == "依据第四十二条回答"
    # Prompt 中拼入【参考依据】与来源标注
    system_user = llm.streamed[0][-1].content
    assert "【参考依据】" in system_user and "【来源：专利法.txt】" in system_user
    assert any(e.type == "delta" for e in events)


def test_answer_generator_not_implemented_generates_explanation(monkeypatch: pytest.MonkeyPatch):
    events = _events_of(monkeypatch, __import__("app.agent.nodes.answer_generator_agent", fromlist=["x"]))
    llm = StreamingFakeLLM(stream_text="网络搜索尚未开通")
    asyncio.run(AnswerGeneratorAgent(LLMService(llm))(_state(
        original_query="搜一下最新法规",
        last_capability="web_search",
        capability_result={"capability": "web_search", "status": CAPABILITY_NOT_IMPLEMENTED,
                           "evidence": [], "citations": [], "metadata": {}},
    )))
    # 说明性回答经 fallback 提示组装（未开通指引在 user 消息），带 delta 流式
    assert "尚未开通" in llm.streamed[0][-1].content
    assert any(e.type == "delta" for e in events)


def test_answer_generator_emits_regenerating_on_retry(monkeypatch: pytest.MonkeyPatch):
    events = _events_of(monkeypatch, __import__("app.agent.nodes.answer_generator_agent", fromlist=["x"]))
    asyncio.run(AnswerGeneratorAgent(LLMService(StreamingFakeLLM(stream_text="修正后的回答")))(
        _state(answer_draft="旧稿", grounding_issues=["未注明来源"])))
    assert events[0].type == "regenerating"


# ---- GroundingCheckerAgent ----

def test_grounding_rule_requires_source_marker_with_context():
    checker = GroundingCheckerAgent(LLMService(StreamingFakeLLM()))
    result = asyncio.run(checker(_state(
        answer_draft="根据条文，期限为二十年",  # 缺【来源：标注
        capability_result={"capability": "local_legal_rag", "status": CAPABILITY_SUCCESS,
                           "evidence": [], "citations": [], "metadata": {}},
        evidence=[{"source_name": "专利法.txt", "content": "期限二十年"}],
    )))
    assert result["grounding_passed"] is False
    assert any("来源" in issue for issue in result["grounding_issues"])
    assert result["global_step_count"] == 1  # 打回回路经此计数


def test_grounding_rule_requires_no_evidence_declaration():
    checker = GroundingCheckerAgent(LLMService(StreamingFakeLLM()))
    result = asyncio.run(checker(_state(
        answer_draft="这个问题很难说",
        capability_result={"capability": "local_legal_rag", "status": CAPABILITY_LOCAL_EVIDENCE_INSUFFICIENT,
                           "evidence": [], "citations": [], "metadata": {}},
        evidence=[],
    )))
    assert result["grounding_passed"] is False
    assert any("信息不足" in issue for issue in result["grounding_issues"])


def test_grounding_skips_not_implemented_and_passes_direct():
    checker = GroundingCheckerAgent(LLMService(StreamingFakeLLM(['{"passed": true, "reason": "无编造"}'])))
    skipped = asyncio.run(checker(_state(
        answer_draft="网络搜索功能尚未开通",
        capability_result={"capability": "web_search", "status": CAPABILITY_NOT_IMPLEMENTED,
                           "evidence": [], "citations": [], "metadata": {}},
        evidence=[],
    )))
    assert skipped["grounding_passed"] is True  # 未开通说明跳过校验

    direct = asyncio.run(checker(_state(
        answer_draft="你好，我是法律助手，很高兴为你服务。",
        capability_result={"capability": "direct_answer", "status": CAPABILITY_SUCCESS,
                           "evidence": [], "citations": [], "metadata": {}},
        evidence=[],
    )))
    assert direct["grounding_passed"] is True  # 直接回答按一般标准判（无编造）


def test_grounding_judge_detects_unsupported_claims():
    raw = json.dumps({"passed": False, "unsupported_claims": ["可获双倍赔偿"],
                      "citation_issues": [], "reason": "无依据"}, ensure_ascii=False)
    checker = GroundingCheckerAgent(LLMService(StreamingFakeLLM([raw])))
    result = asyncio.run(checker(_state(
        answer_draft="【来源：专利法.txt】可获双倍赔偿",
        capability_result={"capability": "local_legal_rag", "status": CAPABILITY_SUCCESS,
                           "evidence": [], "citations": [], "metadata": {}},
        evidence=[{"source_name": "专利法.txt", "content": "期限二十年"}],
    )))
    assert result["grounding_passed"] is False
    assert "可获双倍赔偿" in result["grounding_issues"][0]


# ---- FallbackGeneratorAgent / FinalAnswerNode ----

def test_fallback_streams_and_final_node_finalizes(monkeypatch: pytest.MonkeyPatch):
    events = _events_of(monkeypatch, __import__("app.agent.nodes.fallback_generator_agent", fromlist=["x"]))
    llm = StreamingFakeLLM(stream_text="谨慎回答")
    fallback = asyncio.run(FallbackGeneratorAgent(LLMService(llm))(
        _state(answer_draft="旧稿", evidence=[{"source_name": "专利法.txt", "content": "二十年"}],
               grounding_issues=["引用不符"])))
    assert fallback["answer_draft"] == "谨慎回答"
    assert events[0].type == "regenerating"  # 旧草稿已流出 → 先清空

    final = asyncio.run(FinalAnswerNode(CitationService())(
        _state(answer_draft="谨慎回答", evidence=[{"source_name": "专利法.txt", "content": "二十年",
                                                   "chunk_id": "c1", "document_id": "d1"}])))
    assert final["answer"] == "谨慎回答"  # 端口输出键
    assert final["final_answer"] == "谨慎回答"
    assert final["citations"][0]["citation_id"] == "1"
