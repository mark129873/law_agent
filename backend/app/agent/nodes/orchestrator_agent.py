"""顶层编排节点（BE-036，设计 §12）：轻量决策下一步能力。"""

from __future__ import annotations

from app.agent.config import AgentConfig
from app.agent.constants import ACTION_FINISH
from app.agent.prompts.orchestrator import build_orchestrator_messages
from app.agent.schemas import OrchestratorDecision
from app.agent.services.llm_service import LLMService
from app.agent.state import AgentState
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer


class OrchestratorAgent:
    """根据路由结果 + 最近能力结果 + 预算决定下一步（设计 §12）。

    一期不做（设计 §12）：复杂 Skill 编排、多 Agent delegation、
    动态 Plugin discovery、MCP tool planning。
    """

    def __init__(self, llm: LLMService, config: AgentConfig) -> None:
        self._llm = llm
        self._config = config

    async def __call__(self, state: AgentState) -> dict:
        timer = Timer()
        step_count = int(state.get("global_step_count") or 0)
        max_steps = int(state.get("max_global_steps") or self._config.max_global_steps)

        # 预算双保险第二道（第一道在 grounding 条件边，ADR-0007）：
        # 步数耗尽时无视 LLM 输出强制 finish——编排决策可以错，死循环不可以有
        if step_count >= max_steps:
            return {
                "current_action": ACTION_FINISH,
                "action_reason": "步数预算耗尽，强制汇总生成回答",
                "trace": [
                    make_trace(
                        "orchestrator_agent", "success", timer.elapsed_ms(),
                        extra={"forced_finish": True, "global_step_count": step_count},
                    )
                ],
            }

        decision = await self._llm.structured_invoke(
            build_orchestrator_messages(
                question=state.get("original_query") or state["question"],
                intent=state.get("intent") or "",
                request_type=state.get("request_type") or "",
                last_capability=state.get("last_capability") or "",
                capability_status=state.get("capability_status") or "",
                global_step_count=step_count,
                max_global_steps=max_steps,
                grounding_issues=state.get("grounding_issues") or None,
            ),
            OrchestratorDecision,
            # 安全默认：finish——已有能力结果时汇总收尾，避免编排失控
            default=OrchestratorDecision(action=ACTION_FINISH, reason="编排解析失败，安全收尾"),
        )
        return {
            "current_action": decision.action,
            "action_reason": decision.reason,
            "trace": [
                make_trace(
                    "orchestrator_agent",
                    "success",
                    timer.elapsed_ms(),
                    extra={
                        "model": self._llm.model_name,
                        "action": decision.action,
                        "reason": decision.reason,
                        "global_step_count": step_count,
                    },
                )
            ],
        }
