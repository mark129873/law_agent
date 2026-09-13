"""直接回答节点（BE-036，设计 §17）：一般性对话不经检索直接流式回答。"""

from __future__ import annotations

import logging

from app.agent.constants import CAPABILITY_SUCCESS
from app.agent.events import emit_event
from app.agent.prompts.direct_answer import build_direct_messages
from app.agent.services.llm_service import LLMService
from app.agent.state import AgentState
from app.agent.utils.think_utils import emit_think
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer
from app.domain.services.qa_workflow import QaStreamEvent

logger = logging.getLogger("app.agent.nodes.direct_answer")


class DirectAnswerAgent:
    """适用于无需 Local RAG / Web / Plugin 的问题（问候/概念解释/系统说明）。

    为什么本节点自己流式：直接回答没有后续"汇总生成"环节，
    这里就是回答的诞生地——流式输出保证首字延迟最低；
    RAG 路径的最终回答则由 answer_generator_agent 统一流式（单一出口）。
    """

    def __init__(self, llm: LLMService) -> None:
        self._llm = llm

    async def __call__(self, state: AgentState) -> dict:
        timer = Timer()
        # 打回重答（grounding 失败后重走 direct）：清空旧增量前通知前端
        if state.get("answer_draft"):
            emit_event(QaStreamEvent(type="regenerating"))
            # 思考内容（BE-042）：重写是关键流转，前端思考块可见
            emit_think("direct_answer_agent", "回答未通过校验（不得编造法条），自动重写中")

        messages = build_direct_messages(
            state.get("original_query") or state["question"],
            history=state.get("history"),
            feedback=_pending_feedback(state),
        )
        logger.info(
            "Agent direct answer started",
            extra={"service": "agent", "model": self._llm.model_name, "is_retry": bool(state.get("answer_draft"))},
        )
        writer_chunks: list[str] = []
        async for chunk in self._llm.stream(messages):
            writer_chunks.append(chunk)
            emit_event(QaStreamEvent(type="delta", content=chunk))
        answer = "".join(writer_chunks)
        return {
            "capability_result": {
                "capability": "direct_answer",
                "status": CAPABILITY_SUCCESS,
                "content": answer,
            },
            "answer_draft": answer,
            "trace": [
                make_trace(
                    "direct_answer_agent",
                    "success",
                    timer.elapsed_ms(),
                    extra={"model": self._llm.model_name, "answer_length": len(answer)},
                )
            ],
        }


def _pending_feedback(state: AgentState) -> str:
    """取 grounding 打回的修正反馈（消费后清空由调用方状态覆盖）。"""
    return "；".join(state.get("grounding_issues") or [])
