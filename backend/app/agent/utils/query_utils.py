"""检索查询汇总工具（BE-032，设计 §26）。

纯函数、无 IO：把四类查询变体合并为去重后的检索查询列表。
为什么独立成 utils 而放进节点：合并规则有独立测试价值，
节点只做编排，规则可单测可复用。
"""

from __future__ import annotations

from app.agent.constants import (
    QUERY_TYPE_EXPANSION,
    QUERY_TYPE_ORIGINAL,
    QUERY_TYPE_REWRITE,
    QUERY_TYPE_SUBQUERY,
)


def normalize_query_text(query: str) -> str:
    """查询文本归一（去首尾空白 + 压缩连续空白），作为去重键。"""
    return " ".join(query.split())


def collect_retrieval_queries(
    base_query: str,
    rewritten_queries: list[str],
    sub_queries: list[str],
    expanded_queries: list[str],
    *,
    include_original: bool = True,
    exclude_texts: set[str] | None = None,
    max_queries: int = 8,
) -> list[dict[str, str]]:
    """合并四类查询变体为去重后的检索查询列表（设计 §26）。

    为什么按 original→rewrite→subquery→expansion 固定顺序：检索无
    先后依赖（并行执行），但顺序稳定可让 trace 与事件序列可复现。
    exclude_texts 用于恢复轮排除已检索过的查询文本（设计 §36：
    避免重复执行同样失败的策略）；max_queries 截断保护检索成本
    （设计 §49 性能约束）。
    """
    grouped: list[tuple[str, str]] = []
    if include_original and base_query.strip():
        grouped.append((QUERY_TYPE_ORIGINAL, base_query))
    for query in rewritten_queries:
        grouped.append((QUERY_TYPE_REWRITE, query))
    for query in sub_queries:
        grouped.append((QUERY_TYPE_SUBQUERY, query))
    for query in expanded_queries:
        grouped.append((QUERY_TYPE_EXPANSION, query))

    exclude = {normalize_query_text(text) for text in (exclude_texts or set())}
    seen: set[str] = set()
    collected: list[dict[str, str]] = []
    for query_type, raw in grouped:
        key = normalize_query_text(raw)
        if not key or key in seen or key in exclude:
            continue
        seen.add(key)
        collected.append({"query": raw.strip(), "query_type": query_type})
    return collected[:max_queries]
