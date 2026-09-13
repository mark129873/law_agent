"""回答生成节点（BE-036，设计 §18）：能力结果 → 最终回答草稿（流式）。"""

from __future__ import annotations

import logging

from app.agent.constants import (
    ACTION_DIRECT_ANSWER,
    CAPABILITY_DISABLED,
    CAPABILITY_NOT_IMPLEMENTED,
    CAPABILITY_SUCCESS,
)
from app.agent.events import emit_event
from app.agent.prompts.answer_generator import build_answer_messages
from app.agent.prompts.direct_answer import build_direct_messages
from app.agent.prompts.fallback_generator import build_fallback_messages
from app.agent.services.llm_service import LLMService
from app.agent.state import AgentState
from app.agent.utils.evidence_utils import format_evidence_context
from app.agent.utils.think_utils import emit_think
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer
from app.domain.services.qa_workflow import QaStreamEvent

logger = logging.getLogger("app.agent.nodes.answer_generator")


class AnswerGeneratorAgent:
    """finish 路径的唯一流式出口（架构映射决策 4）。

    四种情形：
    1. 直接回答已有完整草稿（direct 能力已流式输出）→ 透传，不再调模型；
    2. Web/Plugin 未开通（NOT_IMPLEMENTED/DISABLED）→ 流式生成说明性回答；
    3. 有知识库证据（含部分证据）→ 依据 BE-017 策略流式生成；
    4. 走过检索但无任何命中 → 流式生成"信息不足"声明（BE-017 契约）。
    """

    def __init__(self, llm: LLMService) -> None:
        self._llm = llm

    async def __call__(self, state: AgentState) -> dict:
        timer = Timer()
        capability = state.get("capability_result") or {}
        status = capability.get("status") or ""
        evidence = list(state.get("evidence") or [])
        context = format_evidence_context(evidence)
        question = state.get("original_query") or state["question"]
        is_retry = bool(state.get("answer_draft"))

        # 情形 1：直接回答透传（草稿已流式输出过，不重复推增量、不重复调模型）
        if capability.get("capability") == "direct_answer" and status == CAPABILITY_SUCCESS and capability.get("content"):
            return {
                "answer_draft": capability["content"],
                "trace": [
                    make_trace("answer_generator_agent", "success", timer.elapsed_ms(),
                               extra={"mode": "passthrough", "answer_length": len(capability["content"])})
                ],
            }

        # 未开通能力（Web/Plugin Stub）→ 说明性回答（规则 3，PRODUCT.md §3）
        if status in (CAPABILITY_NOT_IMPLEMENTED, CAPABILITY_DISABLED):
            feature = "网络搜索" if state.get("last_capability") == "web_search" else "插件能力"
            messages = build_fallback_messages(
                question,
                context="",
                issues=[f"{feature}功能尚未开通，请告知用户该功能暂不可用，"
                        f"并建议：法律问题可直接提出，系统将基于本地法律知识库回答。"],
            )
            mode = f"not_implemented:{feature}"
        else:
            # 情形 3/4：依据 BE-017 策略生成（context 为空走信息不足声明）
            messages = build_answer_messages(
                question=question,
                context=context,
                history=state.get("history"),
                feedback="；".join(state.get("grounding_issues") or []) if is_retry else "",
            )
            mode = "rag_answer" if context else "insufficient_answer"

        # 打回重生成前必推 regenerating（前端清空已渲染增量，SSE 契约）
        if is_retry:
            emit_event(QaStreamEvent(type="regenerating"))
            # 思考内容（BE-042）：重写是关键流转，前端思考块可见
            emit_think("answer_generator_agent", "回答未通过依据校验，根据校验反馈自动重写中")

        logger.info(
            "Agent answer generation started",
            extra={"service": "agent", "model": self._llm.model_name, "mode": mode, "is_retry": is_retry},
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
                    "answer_generator_agent",
                    "success",
                    timer.elapsed_ms(),
                    extra={"model": self._llm.model_name, "mode": mode, "answer_length": len(answer)},
                )
            ],
        }
