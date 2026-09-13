"""证据候选去重工具（BE-032，设计 §33）。

去重键优先级：chunk_id > (document_id + chunk_index) > content_hash；
同一 chunk 被多个 Query 命中时合并 matched_queries（相关度信号）。
"""

from __future__ import annotations

import hashlib

from app.agent.subgraphs.legal_rag.state import EvidenceItem

# 分数字段：合并时取最大值（与 RagService 多子查询合并口径一致）
_SCORE_FIELDS = ("rrf_score", "rerank_score", "dense_score", "bm25_score")


def content_hash(content: str) -> str:
    """内容指纹：SHA1 前 16 位即可区分候选（非安全场景，求短求快）。"""
    return hashlib.sha1(content.encode("utf-8")).hexdigest()[:16]


def _key_of(item: EvidenceItem) -> tuple[str, str]:
    """按优先级构造去重键（设计 §33）：chunk_id > doc+index > content_hash。"""
    chunk_id = str(item.get("chunk_id") or "")
    if chunk_id:
        return ("chunk_id", chunk_id)
    document_id = str(item.get("document_id") or "")
    chunk_index = str(item.get("metadata", {}).get("chunk_index", ""))
    if document_id and chunk_index:
        return ("doc_chunk", f"{document_id}:{chunk_index}")
    return ("content_hash", content_hash(str(item.get("content") or "")))


def dedup_candidates(candidates: list[EvidenceItem]) -> list[EvidenceItem]:
    """按优先级键去重合并候选（设计 §33）。

    为什么合并而不是丢弃重复项：同一 chunk 被多个 Query 命中说明
    相关度高，matched_queries 的并集供 grader 与 trace 消费；
    分数取最大值（跨 Query 的 RRF 分可比性有限，取 max 是保守策略，
    与既有 RagService 多子查询合并口径一致）；保持首见顺序稳定。
    """
    merged: dict[tuple[str, str], EvidenceItem] = {}
    order: list[tuple[str, str]] = []
    for item in candidates:
        key = _key_of(item)
        first_query = str(item.get("query") or "")
        if key not in merged:
            copy = dict(item)
            # 首见条目自己的命中查询也计入 matched_queries
            copy["matched_queries"] = [first_query] if first_query else []
            merged[key] = copy
            order.append(key)
            continue

        existing = merged[key]
        matched = {q for q in (existing.get("matched_queries") or []) if q}
        if first_query:
            matched.add(first_query)
        matched.update(q for q in (item.get("matched_queries") or []) if q)
        existing["matched_queries"] = sorted(matched)
        # 首见条目缺 query 字段时补齐（保证 trace 可追溯首次命中查询）
        if not existing.get("query") and first_query:
            existing["query"] = first_query
        for field in _SCORE_FIELDS:
            existing[field] = max(existing.get(field) or 0.0, item.get(field) or 0.0)
    return [merged[key] for key in order]
