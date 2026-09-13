"""策略路由节点（BE-034，设计 §22/约束 14/15）：统一执行首轮计划与恢复计划。"""

from __future__ import annotations

from app.agent.subgraphs.legal_rag.state import LegalRAGState
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer

# 恢复动作 → 计划开关的映射（RecoveryPlan.actions 是动作名，计划用 use_* 布尔量）
_ACTION_FLAGS = {
    "query_rewrite": "use_query_rewrite",
    "subquery": "use_subquery",
    "query_expansion": "use_query_expansion",
}


class StrategyRouterNode:
    """归一化当前计划，供条件边 fan-out（设计 §22：current_plan 统一首轮与恢复）。

    为什么本节点只归一化计划而不直接选路：fan-out 的目标列表由条件边
    路由函数（route_strategies）读取归一化后的 current_plan 计算——
    节点与路由函数职责分离，路由规则可独立单测。
    """

    async def __call__(self, state: LegalRAGState) -> dict:
        timer = Timer()
        recovery = state.get("recovery_plan")
        if recovery:
            # 恢复计划：动作名 → 布尔开关；原始问题首轮已检索过，不再重复
            actions = set(recovery.get("actions") or [])
            current: dict = {
                "use_original_query": False,
                "use_query_rewrite": "query_rewrite" in actions,
                "use_subquery": "subquery" in actions,
                "use_query_expansion": "query_expansion" in actions,
                "target_evidence": recovery.get("missing_evidence") or [],
                "reason": recovery.get("reason") or "",
                "is_recovery": True,
            }
        else:
            # 首轮：直接采用检索计划
            current = dict(state.get("retrieval_plan") or {})
            current["is_recovery"] = False
        return {
            "current_plan": current,
            "rag_trace": [
                make_trace(
                    "strategy_router_node",
                    "success",
                    timer.elapsed_ms(),
                    extra={
                        "is_recovery": bool(current.get("is_recovery")),
                        "strategies": [flag for flag in _ACTION_FLAGS.values() if current.get(flag)],
                    },
                )
            ],
        }


def route_strategies(state: LegalRAGState) -> list[str]:
    """策略条件边路由：多选 fan-out 到对应查询变体节点（约束 15）。

    为什么返回列表：LangGraph 条件边返回多个目标即并行执行（fan-out），
    全部分支汇入 hybrid_retriever_node（约束 16：所有子查询进同一混合检索）。
    为什么无变体时直接进检索：计划只启用原始问题（或解析失败的默认值）
    时，不需要任何 LLM 变体节点——省掉三次无效模型调用。
    """
    plan = state.get("current_plan") or {}
    targets: list[str] = []
    for action, flag in _ACTION_FLAGS.items():
        if plan.get(flag):
            targets.append(
                {"query_rewrite": "query_rewrite_agent", "subquery": "subquery_generator_agent",
                 "query_expansion": "query_expansion_agent"}[action]
            )
    return targets or ["hybrid_retriever_node"]
