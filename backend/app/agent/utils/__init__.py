"""Agent 工具函数包：纯函数、无 IO、可独立单测（设计 §5 utils）。"""

from app.agent.utils.dedup_utils import content_hash, dedup_candidates
from app.agent.utils.evidence_utils import (
    chunk_to_evidence,
    evidence_to_source,
    format_evidence_context,
)
from app.agent.utils.query_utils import collect_retrieval_queries, normalize_query_text
from app.agent.utils.timing_utils import Timer
from app.agent.utils.trace_utils import make_trace

__all__ = [
    "Timer",
    "chunk_to_evidence",
    "collect_retrieval_queries",
    "content_hash",
    "dedup_candidates",
    "evidence_to_source",
    "format_evidence_context",
    "make_trace",
    "normalize_query_text",
]
