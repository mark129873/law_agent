"""Plugin Stub 节点（BE-037，设计 §16）：一期只返回 NOT_IMPLEMENTED。

强制约束 9/26：不得动态 import、exec、git clone 或加载任何外部代码
——本节点是纯静态结果返回。
"""

from __future__ import annotations

from app.agent.constants import CAPABILITY_NOT_IMPLEMENTED
from app.agent.state import AgentState
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer


class PluginStubNode:
    """Plugin / Skill 能力占位：返回未实现结果。"""

    async def __call__(self, state: AgentState) -> dict:
        timer = Timer()
        return {
            "capability_result": {
                "capability": "plugin",
                "status": CAPABILITY_NOT_IMPLEMENTED,
                "content": None,
                "evidence": [],
                "citations": [],
                "metadata": {"reason": "plugin runtime is not implemented in phase 1"},
            },
            "trace": [
                make_trace("plugin_stub_node", "success", timer.elapsed_ms(),
                           extra={"status": CAPABILITY_NOT_IMPLEMENTED})
            ],
        }
