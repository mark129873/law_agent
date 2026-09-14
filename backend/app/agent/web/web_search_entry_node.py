"""Web Search 入口节点（BE-037，设计 §15.1）：检查用户 Web Search 开关。

一期仅保留入口：开关关闭（默认）→ DISABLED；开启 → 进入 Stub
（本节点不访问任何网络）。
"""

from __future__ import annotations

from app.agent.constants import CAPABILITY_DISABLED
from app.agent.state import AgentState
from app.agent.utils.think_utils import emit_think
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer


class WebSearchEntryNode:
    """开关检查：web_search_enabled=false → 直接产出 DISABLED 结果。"""

    async def __call__(self, state: AgentState) -> dict:
        timer = Timer()
        enabled = bool(state.get("web_search_enabled"))
        if enabled:
            # 开关开启 → 继续进入 Stub（Stub 返回 NOT_IMPLEMENTED）
            return {
                "trace": [
                    make_trace("web_search_entry_node", "success", timer.elapsed_ms(),
                               extra={"enabled": True})
                ]
            }
        # 思考内容（BE-042）：未开通说明——配置关闭（DISABLED）分支
        emit_think("web_search_entry_node", "网络搜索未开通（配置关闭），跳过外部检索")
        return {
            "capability_result": {
                "capability": "web_search",
                "status": CAPABILITY_DISABLED,
                "content": None,
                "evidence": [],
                "citations": [],
                "metadata": {"reason": "web search disabled by configuration"},
            },
            "trace": [
                make_trace("web_search_entry_node", "success", timer.elapsed_ms(),
                           extra={"enabled": False, "status": CAPABILITY_DISABLED})
            ],
        }
