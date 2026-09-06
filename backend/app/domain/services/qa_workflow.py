"""问答工作流领域端口。

为什么需要该端口：ChatService（应用层）需要执行问答工作流，
但不应知道工作流由哪个引擎实现（当前是 LangGraph，未来可能是
自研编排）。端口只声明执行问答所需的两个方法，
LangGraph 的 CompiledStateGraph 结构上天然满足本协议。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class QaStreamEvent:
    """流式问答的领域事件：工作流对外的统一输出单元。

    为什么用类型化事件而不是裸字符串：流式回答除增量文本外，
    还需携带"参考来源"这类结构化数据（参考文档展示，FE-011）；
    事件类型化后，服务层与引擎实现之间的契约明确可校验，
    新增事件种类时只扩展本类，端口方法签名不变（开闭原则）。

    DDD 说明：本类是领域层值对象（不可变、无身份、按值相等），
    零技术依赖，任何工作流引擎实现都必须以它为流式输出单位。
    """

    # delta：一段增量回答文本；sources：本次回答的参考来源（检索顺序即序号）
    type: Literal["delta", "sources"]
    content: str = ""
    # 每项 {"source": 文件名, "content": 命中内容}；用 tuple 保持不可变
    sources: tuple[dict[str, str], ...] = ()


# runtime_checkable：允许装配点与测试用 isinstance 校验实现方满足端口
# （仅检查方法存在性；签名正确性由调用约定与测试保证）
@runtime_checkable
class QaWorkflow(Protocol):
    """问答工作流契约：非流式执行 + 流式执行。"""

    async def ainvoke(self, input: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """执行一次问答，返回最终状态（含 answer）。"""

    def astream(self, input: dict[str, Any], **kwargs: Any) -> AsyncIterator[QaStreamEvent]:
        """流式执行问答（stream_mode=custom 时逐事件产出 QaStreamEvent）。"""
