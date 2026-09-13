"""动作路由节点（BE-036，设计 §13/§46.1）：确定性 Action → 节点映射。

不调用 LLM（约束 3）：只根据 orchestrator 写入的 current_action
做映射；真正的分派由图的条件边（route_action）完成，本节点只负责
登记"当前执行的能力"供 observation 归一。
"""

from __future__ import annotations

from app.agent.state import AgentState
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer

# 设计 §46.1 的映射表：Action 名 → 图节点名
ACTION_TARGETS: dict[str, str] = {
    "local_rag": "legal_rag_subgraph",
    "plugin": "plugin_entry_node",
    "web_search": "web_search_entry_node",
    "direct_answer": "direct_answer_agent",
    "finish": "answer_generator_agent",
}


class ActionRouterNode:
    """登记当前能力（last_capability），映射规则由 route_action 消费。"""

    async def __call__(self, state: AgentState) -> dict:
        timer = Timer()
        action = state.get("current_action") or "finish"
        return {
            "last_capability": action,
            "trace": [
                make_trace(
                    "action_router_node",
                    "success",
                    timer.elapsed_ms(),
                    extra={"action": action, "target": ACTION_TARGETS.get(action, "answer_generator_agent")},
                )
            ],
        }


def route_action(state: AgentState) -> str:
    """主图条件边：current_action → 目标节点（设计 §46.1）。

    为什么映射表模块级导出：BE-038 的图装配与 BE-039 的路由测试
    都要消费同一份映射，避免两处硬编码漂移。
    """
    action = state.get("current_action") or "finish"
    return ACTION_TARGETS.get(action, "answer_generator_agent")
