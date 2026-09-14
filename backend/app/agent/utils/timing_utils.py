"""计时工具（BE-032）：节点起止计时的最小实现。"""

from __future__ import annotations

import time


class Timer:
    """简单秒表：status 事件与 trace 共用同一计时源（设计 §48）。

    为什么不用装饰器：节点执行由图构建器的统一包装器计时
    （BE-041），Timer 供节点内部对局部阶段（如单次 LLM 调用）补充计时。
    """

    def __init__(self) -> None:
        self._started_at = time.perf_counter()

    def elapsed_ms(self) -> int:
        """自创建以来经过的毫秒数（整数，供展示与 trace）。"""
        return int((time.perf_counter() - self._started_at) * 1000)
