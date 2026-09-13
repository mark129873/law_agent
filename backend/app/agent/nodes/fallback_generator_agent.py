"""兜底回答节点（BE-036，设计 §3 GC→FB 路径）：grounding 预算耗尽后的谨慎回答。"""

from __future__ import annotations

import logging

from app.agent.events import emit_event
from app.agent.prompts.fallback_generator import build_fallback_messages
from app.agent.services.llm_service import LLMService
from app.agent.state import AgentState
from app.agent.utils.evidence_utils import format_evidence_context
from app.agent.utils.think_utils import emit_think
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer
from app.domain.services.qa_workflow import QaStreamEvent

logger = logging.getLogger("app.agent.nodes.fallback_generator")


class FallbackGeneratorAgent:
    """基于已有可靠证据生成谨慎回答（预算耗尽，不再重试）。

    为什么打回不回 orchestrator 而直接流式（设计 §3）：到达本节点时
    global 预算已耗尽，任何再编排都会被强制 finish——直接生成
    兜底回答是预算约束下的确定收尾。
    """

    def __init__(self, llm: LLMService) -> None:
        self._llm = llm

    async def __call__(self, state: AgentState) -> dict:
        timer = Timer()
        # 思考内容（BE-042）：兜底触发是关键流转，前端思考块必须可见
        emit_think("fallback_generator_agent", "回答依据校验未通过且重试预算耗尽，基于已有证据生成谨慎回答")
        # 旧草稿已流式输出过 → 先推 regenerating（前端清空增量，防拼接）
        if state.get("answer_draft"):
            emit_event(QaStreamEvent(type="regenerating"))
        messages = build_fallback_messages(
            state.get("original_query") or state["question"],
            context=format_evidence_context(list(state.get("evidence") or [])),
            issues=list(state.get("grounding_issues") or []),
        )
        logger.info(
            "Agent fallback answer started",
            extra={"service": "agent", "model": self._llm.model_name},
        )
        chunks: list[str] = []
        async for chunk in self._llm.stream(messages):
            chunks.append(chunk)
            emit_event(QaStreamEvent(type="delta", content=chunk))
        answer = "".join(chunks)
        return {
            "answer_draft": answer,
            "trace": [
                make_trace(
                    "fallback_generator_agent",
                    "success",
                    timer.elapsed_ms(),
                    extra={"model": self._llm.model_name, "answer_length": len(answer)},
                )
            ],
        }
