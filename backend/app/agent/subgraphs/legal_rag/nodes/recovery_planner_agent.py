"""恢复规划节点（BE-034，设计 §36/§37）：检索不足时生成本地补救计划。

为什么没有 web_search/plugin/relax_filter 动作（约束：设计 §36）：
Local RAG 恢复循环只能动"查询怎么写"，不能动"去哪查"——
本地知识库边界不被恢复逻辑突破；外部证据缺口以
suggested_external_queries 透传给主图（一期不使用）。
"""

from __future__ import annotations

from app.agent.services.llm_service import LLMService
from app.agent.subgraphs.legal_rag.config import LegalRAGConfig
from app.agent.subgraphs.legal_rag.prompts.recovery_planner import build_recovery_messages
from app.agent.subgraphs.legal_rag.schemas import RecoveryPlan
from app.agent.subgraphs.legal_rag.state import LegalRAGState
from app.agent.utils.think_utils import emit_think
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer

# 全部可用动作（安全默认从中选未执行过的）
_ALL_ACTIONS = ("query_rewrite", "subquery", "query_expansion")


class RecoveryPlannerAgent:
    """分析失败原因 → 生成下一轮 Recovery Plan（actions 是多选动作名）。"""

    def __init__(self, llm: LLMService, config: LegalRAGConfig) -> None:
        self._llm = llm
        self._config = config

    async def __call__(self, state: LegalRAGState) -> dict:
        timer = Timer()
        retry = int(state.get("retry_count") or 0) + 1
        original = state.get("original_query") or state.get("normalized_query") or ""
        missing = list(state.get("missing_evidence") or [])
        executed = self._executed_strategies(state)
        # 安全默认：优先选未执行过的动作，全部执行过则扩展术语（最常见的补救）
        plan = await self._llm.structured_invoke(
            build_recovery_messages(original, missing, executed, retry),
            RecoveryPlan,
            default=RecoveryPlan(
                actions=[self._default_actions(executed)[0]],
                reason="规划解析失败，默认选择未执行过的补救动作",
                missing_evidence=missing,
            ),
        )
        # 思考内容（BE-042）：恢复计划理由（模型原文，统一截断打印）
        emit_think("recovery_planner_agent", f"恢复计划：{plan.reason}")
        return {
            "recovery_plan": {
                "actions": list(plan.actions),
                "reason": plan.reason,
                "missing_evidence": plan.missing_evidence,
            },
            "retry_count": retry,
            "rag_trace": [
                make_trace(
                    "recovery_planner_agent",
                    "success",
                    timer.elapsed_ms(),
                    extra={
                        "model": self._llm.model_name,
                        "retry_count": retry,
                        "actions": list(plan.actions),
                        "executed_strategies": executed,
                    },
                )
            ],
        }

    @staticmethod
    def _executed_strategies(state: LegalRAGState) -> list[str]:
        """从已产出的查询变体反推执行过的策略（设计 §36：避免重复失败策略）。"""
        executed: list[str] = []
        if state.get("rewritten_queries"):
            executed.append("query_rewrite")
        if state.get("sub_queries"):
            executed.append("subquery")
        if state.get("expanded_queries"):
            executed.append("query_expansion")
        return executed

    @staticmethod
    def _default_actions(executed: list[str]) -> list[str]:
        """安全默认动作：第一个未执行过的动作；全部执行过则扩展术语。"""
        untouched = [action for action in _ALL_ACTIONS if action not in executed]
        return untouched or ["query_expansion"]
