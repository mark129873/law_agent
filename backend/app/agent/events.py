"""流式事件发射助手（BE-034）。

为什么需要包装：get_stream_writer 只在图执行的 runnable 上下文内
可用，图外直调（单元测试、非流式 ainvoke 的部分场景）会抛
RuntimeError——事件是"增强输出"而非业务必需，图外安全丢弃即可，
节点逻辑不应为此分支。
"""

from __future__ import annotations

import logging

from langgraph.config import get_stream_writer

from app.domain.services.qa_workflow import QaStreamEvent

logger = logging.getLogger("app.agent.events")


def emit_event(event: QaStreamEvent) -> None:
    """在图执行上下文中推送领域事件；图外调用安全丢弃（不抛错）。"""
    try:
        get_stream_writer()(event)
    except RuntimeError:
        # 不在 runnable 上下文（单元测试直调节点）——无流通道，事件无处可去
        logger.debug("Stream event dropped outside runnable context", extra={"event_type": event.type})
