"""当前节点 span 上下文（BE-043）。

为什么独立小模块：with_node_status 包装器压栈/弹栈 span，LLMService
读取栈顶记录 generation——两者是 agent 层内"父 span 挂靠"的协作方，
ContextVar 保证跨 asyncio 任务（适配器的图任务）继承与隔离，
且子节点结束后恢复父级（token reset 语义）。
与 domain/services/trace_sink.py 的 trace_sink_var 分工：那个是
"请求级 sink"（应用层注入），这个是"节点级 span"（agent 层内部流转）。
"""

from __future__ import annotations

from contextvars import ContextVar

from app.domain.services.trace_sink import TraceSpan

# 当前最内层节点 span（None = 无 sink 或当前不在任何节点内）
trace_span_var: ContextVar[TraceSpan | None] = ContextVar("trace_span", default=None)


def current_trace_span() -> TraceSpan | None:
    """读取当前最内层节点 span；LLM generation 应挂靠其下。"""
    return trace_span_var.get()
