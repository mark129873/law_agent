"""问答工作流领域端口。

为什么需要该端口：ChatService（应用层）需要执行问答工作流，
但不应知道工作流由哪个引擎实现（当前是 LangGraph，未来可能是
自研编排）。端口只声明执行问答所需的两个方法，
LangGraph 的 CompiledStateGraph 结构上天然满足本协议。
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol


class QaWorkflow(Protocol):
    """问答工作流契约：非流式执行 + 流式执行。"""

    async def ainvoke(self, input: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """执行一次问答，返回最终状态（含 answer）。"""

    def astream(self, input: dict[str, Any], **kwargs: Any) -> AsyncIterator[Any]:
        """流式执行问答（stream_mode=custom 时逐 token 产出）。"""
