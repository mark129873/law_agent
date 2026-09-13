"""证据重排节点（BE-034，设计 §32/§32.1/§33）：聚合去重 + 统一 rerank。

为什么是原 evidence_aggregator 与 reranker 的合并节点（约束 12）：
"合并候选"与"重排候选"是同一个数据加工阶段的两步，拆开只会
多一次全量状态搬运；合并后职责边界依然清晰——本节点回答
"哪些证据更相关"，"证据够不够回答"由独立的 evidence_grader_agent
回答（约束 13）。
"""

from __future__ import annotations

from app.agent.services.reranker_service import RerankerService
from app.agent.subgraphs.legal_rag.config import LegalRAGConfig
from app.agent.subgraphs.legal_rag.state import EvidenceItem, LegalRAGState
from app.agent.utils.dedup_utils import dedup_candidates
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer


class EvidenceRankingNode:
    """flatten → 去重合并 → 以 original_query 统一重排 → top-k（设计 §32）。"""

    def __init__(self, reranker: RerankerService, config: LegalRAGConfig) -> None:
        self._reranker = reranker
        self._config = config

    async def __call__(self, state: LegalRAGState) -> dict:
        timer = Timer()
        raw_candidates = list(state.get("retrieval_candidates") or [])
        candidates: list[EvidenceItem] = dedup_candidates(raw_candidates)
        # 统一 rerank 用 original_query（约束 18）：SubQuery 用于召回，
        # 原始问题才代表用户真实意图的最终相关性
        original = state.get("normalized_query") or state.get("original_query") or ""
        result = await self._reranker.rerank(original, candidates, top_n=self._config.rerank_top_k)
        return {
            "ranked_evidence": result.items,
            "rag_trace": [
                make_trace(
                    "evidence_ranking_node",
                    "success",
                    timer.elapsed_ms(),
                    extra={
                        "input_count": len(raw_candidates),
                        "dedup_count": len(candidates),
                        "rerank_count": len(result.items),
                        "reranker_degraded": result.degraded,
                    },
                )
            ],
        }
