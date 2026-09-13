"""Web Search Stub 节点（BE-037，设计 §15.2）：一期只返回 NOT_IMPLEMENTED。

强制约束 8/26：禁止实际访问 Web——后续二期把本节点替换为
web_research_subgraph，主图路由接口不变（ADR-0001）。
"""

from __future__ import annotations

from app.agent.constants import CAPABILITY_DISABLED, CAPABILITY_NOT_IMPLEMENTED
from app.agent.state import AgentState
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer


class WebSearchStubNode:
    """开关已开启时的 stub：返回未实现结果（不产生任何网络请求）。"""

    async def __call__(self, state: AgentState) -> dict:
        timer = Timer()
        # 入口已判定 DISABLED 时透传（不覆盖为 NOT_IMPLEMENTED）；
        # 显式回传既有结果——图内本可靠状态保留，显式写出便于直调与测试
        existing = state.get("capability_result") or {}
        if existing.get("capability") == "web_search" and existing.get("status") == CAPABILITY_DISABLED:
            return {
                "capability_result": existing,
                "trace": [
                    make_trace("web_search_stub_node", "success", timer.elapsed_ms(),
                               extra={"status": CAPABILITY_DISABLED, "passthrough": True})
                ]
            }
        return {
            "capability_result": {
                "capability": "web_search",
                "status": CAPABILITY_NOT_IMPLEMENTED,
                "content": None,
                "evidence": [],
                "citations": [],
                "metadata": {"reason": "web search is not implemented in phase 1"},
            },
            "trace": [
                make_trace("web_search_stub_node", "success", timer.elapsed_ms(),
                           extra={"status": CAPABILITY_NOT_IMPLEMENTED})
            ],
        }
