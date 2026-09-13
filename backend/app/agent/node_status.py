"""节点状态包装器（BE-041，设计 §48 + D5）：起止计时 + status 事件 + 结构化日志。

为什么在建造者层统一包装而不是每个节点自报：所有节点零改动即获得
状态推送（DRY），「每个 node 都有状态」由装配机制保证而非约定；
status 事件与 trace/日志共用同一计时源，不会互相矛盾。
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from app.agent.constants import node_label
from app.agent.events import emit_event
from app.agent.utils.timing_utils import Timer
from app.domain.services.qa_workflow import QaStreamEvent

logger = logging.getLogger("app.agent.node_status")

# 图节点函数：接收状态 dict，返回状态增量 dict
NodeFn = Callable[[dict], Awaitable[dict]]


def with_node_status(node_name: str, node_fn: NodeFn) -> NodeFn:
    """包装节点函数：开始推 status(start)，结束推 status(end, 耗时)。

    为什么异常时也推 end：前端的状态行不能因节点失败而永远停留在
    "正在执行"——异常路径推 end 后重新抛出，图引擎按异常收尾。
    为什么这里只做状态与日志：trace 由节点自己写（有业务计数），
    包装器不越权。
    """
    label = node_label(node_name)

    async def _wrapped(state: dict) -> dict:
        emit_event(QaStreamEvent(type="status", node=node_name, label=label, phase="start"))
        logger.info("Agent node started", extra={"service": "agent", "node": node_name})
        timer = Timer()
        try:
            result: dict = await node_fn(state)
        except Exception as error:
            logger.error(
                "Agent node failed",
                extra={"service": "agent", "node": node_name, "error": str(error)},
            )
            emit_event(
                QaStreamEvent(
                    type="status", node=node_name, label=label,
                    phase="end", duration_ms=timer.elapsed_ms(),
                )
            )
            raise
        duration_ms = timer.elapsed_ms()
        logger.info(
            "Agent node completed",
            extra={"service": "agent", "node": node_name, "duration_ms": duration_ms},
        )
        emit_event(
            QaStreamEvent(
                type="status", node=node_name, label=label,
                phase="end", duration_ms=duration_ms,
            )
        )
        return result

    return _wrapped


def add_node_traced(builder: Any, node_name: str, node_fn: NodeFn) -> None:
    """向 StateGraph 注册状态包装后的节点（两个图构建器的统一入口）。"""
    builder.add_node(node_name, with_node_status(node_name, node_fn))
