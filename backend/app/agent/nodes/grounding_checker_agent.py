"""回答依据校验节点（BE-036，设计 §19）：规则档 + LLM judge 档。"""

from __future__ import annotations

import logging

from app.agent.constants import (
    CAPABILITY_NOT_IMPLEMENTED,
    CAPABILITY_SUCCESS,
)
from app.agent.prompts.grounding_checker import build_grounding_messages
from app.agent.schemas import GroundingCheck
from app.agent.services.llm_service import LLMService
from app.agent.state import AgentState
from app.agent.utils.evidence_utils import format_evidence_context
from app.agent.utils.think_utils import emit_think
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer

logger = logging.getLogger("app.agent.nodes.grounding_checker")

# BE-017 表达契约的字面锚点（与 Prompt 约定强耦合，改 Prompt 必须同步）
_SOURCE_MARKER = "【来源："
_NO_EVIDENCE_MARKER = "知识库中暂无相关依据"


class GroundingCheckerAgent:
    """检查 Claim ↔ Evidence / Citation ↔ Source（设计 §19）。

    为什么规则档先行：引用来源存在性、信息不足声明是确定性契约检查，
    零 LLM 成本且不会误判；judge 档处理需要语义理解的 groundedness。
    为什么本节点递增 global_step_count（ADR-0007）：grounding 打回
    orchestrator 的回路不经过 observation_node——若此处不计数，
    "grounding→orchestrator→finish→answer→grounding" 回路没有
    预算消耗，会绕过步数上限死循环。
    """

    def __init__(self, llm: LLMService) -> None:
        self._llm = llm

    async def __call__(self, state: AgentState) -> dict:
        timer = Timer()
        answer = state.get("answer_draft") or ""
        capability = state.get("capability_result") or {}
        status = capability.get("status") or ""
        evidence = list(state.get("evidence") or [])
        context = format_evidence_context(evidence)
        question = state.get("original_query") or state["question"]
        step_count = int(state.get("global_step_count") or 0) + 1

        # 未开通能力的说明性回答无需校验（没有事实断言）
        if status in (CAPABILITY_NOT_IMPLEMENTED,):
            return self._verdict(state, GroundingCheck(passed=True, reason="未开通能力说明，跳过校验"),
                                 step_count, timer, skipped=True)

        # ---- 规则档（确定性契约检查，零成本）----
        issues: list[str] = []
        if status == CAPABILITY_SUCCESS and not answer.strip():
            issues.append("回答为空")
        if context:
            if _SOURCE_MARKER not in answer:
                issues.append("回答引用了参考依据但未注明来源文件（缺少【来源：…】标注）")
        elif capability.get("capability") == "local_legal_rag":
            # 走过检索但证据为空（无命中）：回答必须按 BE-017 契约声明信息不足；
            # 直接回答/未开通能力路径无此要求（ADR-0006 双规则）
            if _NO_EVIDENCE_MARKER not in answer:
                issues.append("知识库无命中但回答未声明信息不足，禁止编造")

        if issues:
            return self._verdict(
                state,
                GroundingCheck(passed=False, citation_issues=issues, reason="表达契约未通过（规则档）"),
                step_count, timer,
            )

        # ---- LLM judge 档（groundedness 语义校验）----
        check = await self._llm.structured_invoke(
            build_grounding_messages(question, context, answer),
            GroundingCheck,
            # 安全默认（设计 §47 精神）：判分失效不拦路——校验是增强而非闸门
            default=GroundingCheck(passed=True, reason="校验器输出不可解析，放行"),
        )
        return self._verdict(state, check, step_count, timer)

    def _verdict(
        self,
        state: AgentState,
        check: GroundingCheck,
        step_count: int,
        timer: Timer,
        skipped: bool = False,
    ) -> dict:
        """统一写出判定与步数；打回反馈写入 grounding_issues 供编排消费。"""
        issues = list(check.unsupported_claims) + list(check.citation_issues)
        # 思考内容（BE-042）：校验判定与理由是思考块最有价值的内容之一，
        # 统一在判定出口发射（规则档/LLM judge/跳过三种路径都经此处）
        if skipped:
            emit_think("grounding_checker_agent", f"依据校验跳过：{check.reason}")
        elif check.passed:
            emit_think("grounding_checker_agent", f"依据校验通过：{check.reason or '回答与依据一致'}")
        else:
            emit_think(
                "grounding_checker_agent",
                f"依据校验未通过：{'；'.join(issues) or check.reason}",
            )
        return {
            "grounding_passed": check.passed,
            "grounding_issues": [] if check.passed else issues or [check.reason or "回答依据校验未通过"],
            "global_step_count": step_count,
            "trace": [
                make_trace(
                    "grounding_checker_agent",
                    "success",
                    timer.elapsed_ms(),
                    extra={
                        "model": self._llm.model_name,
                        "passed": check.passed,
                        "skipped": skipped,
                        "issue_count": len(issues),
                        "global_step_count": step_count,
                    },
                )
            ],
        }
