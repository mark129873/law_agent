"""Plugin 入口节点（BE-037，设计 §16）：保留未来稳定接口。

一期不解析插件请求的细节（不动态 import / exec / 加载外部代码），
直接进入 Stub。
"""

from __future__ import annotations

from app.agent.state import AgentState
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer


class PluginEntryNode:
    """预留接口节点：记录请求即通过（解析逻辑二期实现）。"""

    async def __call__(self, state: AgentState) -> dict:
        timer = Timer()
        return {
            "trace": [
                make_trace("plugin_entry_node", "success", timer.elapsed_ms(),
                           extra={"intent": state.get("intent") or ""})
            ]
        }
