"""流式事件发射机制（BE-034/BE-038）。

为什么用 ContextVar 注入式发射器而不是 langgraph 的 get_stream_writer：
实测（BE-038 探针）langgraph 1.2.11 中，子图节点经 get_stream_writer
推送的 custom 事件**不会上浮**到父图 astream——而 plan/sources 事件
恰恰产自 legal_rag 子图内部。改为构建期注入：适配器（LangGraphQaWorkflow）
在 astream 执行期间把"队列投递函数"放入 ContextVar，所有节点（主图与
子图）统一经 emit_event 发射——ContextVar 随 asyncio 任务上下文自动
传播，天然跨越子图边界，且图外直调（单元测试）安全降级为丢弃。
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Callable

from app.domain.services.qa_workflow import QaStreamEvent

logger = logging.getLogger("app.agent.events")

# 当前执行上下文的事件接收器（None = 无消费者，事件丢弃）
event_emitter_var: ContextVar[Callable[[QaStreamEvent], None] | None] = ContextVar(
    "agent_event_emitter", default=None
)


def emit_event(event: QaStreamEvent) -> None:
    """向当前执行上下文的事件接收器推送领域事件；无消费者时安全丢弃。"""
    emitter = event_emitter_var.get()
    if emitter is None:
        # 非流式上下文（ainvoke/单元测试直调节点）——事件无处可去
        logger.debug("Stream event dropped without consumer", extra={"event_type": event.type})
        return
    emitter(event)
