"""节点 trace 条目构造（BE-032，设计 §48）。"""

from __future__ import annotations

from typing import Any


def make_trace(
    node: str,
    status: str,
    duration_ms: int,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造单条节点 trace：{node, status, duration_ms, ...extra}。

    为什么返回单条 dict 而不是帮节点拼接列表：trace 通道配了
    operator.add 归约器，节点只返回"自己的增量"，归并由引擎完成
    （fan-out 并行写安全，见 legal_rag/state.py）。

    extra 承载设计 §48 的统计字段（input_count/output_count/
    query_count/candidate_count 等）与 LLM 节点的 model/latency。
    """
    entry: dict[str, Any] = {"node": node, "status": status, "duration_ms": duration_ms}
    if extra:
        entry.update(extra)
    return entry
