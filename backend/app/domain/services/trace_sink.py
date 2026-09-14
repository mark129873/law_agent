"""可观测汇领域端口（BE-043）：Langfuse 链路追踪的领域抽象。

为什么端口放在领域层：trace 采集点分布在应用层（ChatService 的请求
生命周期）与 agent 层（节点包装器、LLMService），它们都只依赖本协议；
langfuse SDK 锁在 infrastructure/trace/（DDD 守护测试拦截越界导入），
更换观测平台不动任何业务代码（DIP）。

为什么用 ContextVar 注入（trace_sink_var）：与既有事件发射器
同一机制——sink 由应用层在请求开始时放入上下文，图任务经
asyncio.create_task 继承（创建发生在 set 之后）；禁用/无消费者时为
None，全部上报点廉价跳过（与事件"无消费者安全丢弃"同一语义）。
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Protocol, runtime_checkable


@runtime_checkable
class TraceSpan(Protocol):
    """一个节点执行区间的观测句柄：LLM generation 挂靠其下形成层级。"""

    def record_generation(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        output: str | None,
        duration_ms: int | None = None,
        error: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """记录一次 LLM 调用（模型名 + Prompt 消息 + 输出 + 耗时/错误）。"""

    def end(self, *, duration_ms: int | None = None, error: str | None = None) -> None:
        """结束该节点 span（异常路径也必须调用，error 带原因）。"""


@runtime_checkable
class TraceSink(Protocol):
    """一条请求级 trace 的采集汇：trace → 节点 span → LLM generation 三级。"""

    def start_trace(self, *, session_id: str, question: str) -> None:
        """请求开始：创建 trace（session_id=会话 id，input=问题）。"""

    def start_span(self, *, node: str, parent: TraceSpan | None = None) -> TraceSpan | None:
        """开启一个节点 span；parent 为空挂 trace 根，否则挂指定父 span。"""

    def record_event(self, *, name: str, payload: dict[str, str]) -> None:
        """记录一条流程事件（plan/think/sources/regenerating 等留档）。"""

    def end_trace(
        self,
        *,
        output: str | None = None,
        error: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """请求结束：写 trace 输出（或错误）并关闭；之后 sink 不再可用。"""


# 当前请求的 trace 汇（None = 未启用/无消费者，上报点跳过）
trace_sink_var: ContextVar[TraceSink | None] = ContextVar("trace_sink", default=None)


def current_trace_sink() -> TraceSink | None:
    """读取当前上下文的 trace 汇；无则返回 None（调用方跳过采集）。"""
    return trace_sink_var.get()
