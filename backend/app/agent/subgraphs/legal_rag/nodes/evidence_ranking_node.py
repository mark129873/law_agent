"""证据重排节点（BE-034，设计 §32/§32.1/§33）：聚合去重 + 统一 rerank。

为什么是原 evidence_aggregator 与 reranker 的合并节点（约束 12）：
"合并候选"与"重排候选"是同一个数据加工阶段的两步，拆开只会
多一次全量状态搬运；合并后职责边界依然清晰——本节点回答
"哪些证据更相关"，"证据够不够回答"由独立的 evidence_grader_agent
回答（约束 13）。
"""

from __future__ import annotations

from pathlib import Path

from app.agent.services.reranker_service import RerankerService
from app.agent.subgraphs.legal_rag.config import LegalRAGConfig
from app.agent.subgraphs.legal_rag.state import EvidenceItem, LegalRAGState
from app.agent.utils.dedup_utils import dedup_candidates
from app.agent.utils.think_utils import emit_think
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
        # 粗排→精排：先按 RRF 分预截断到 rerank_max_candidates，
        # 防止多查询候选全量进入远程 Reranker 服务造成请求延迟放大；
        # RRF 序与 rerank 序高度相关，预截断对最终 top-k 质量影响有限
        pre_rerank = sorted(
            candidates, key=lambda item: item.get("rrf_score") or 0.0, reverse=True
        )[: self._config.rerank_max_candidates]
        # 多法源问题需要避免单一法源占满 top-k。只在原问题/计划明确点名至少两个
        # 候选来源时启用来源覆盖：重排器已经一次性为候选打分，因此扩大返回数量
        # 不会新增 HTTP 请求；这是应用层的证据选择策略，保持服务层只负责排序。
        source_query = " ".join(
            [
                str(state.get("original_query") or ""),
                str(state.get("normalized_query") or ""),
                " ".join(str(item) for item in (state.get("current_plan") or {}).get("target_evidence") or []),
            ]
        )
        explicit_sources = self._explicit_source_keys(pre_rerank, source_query)
        diversify_sources = len(explicit_sources) >= 2
        result = await self._reranker.rerank(
            original,
            pre_rerank,
            top_n=len(pre_rerank) if diversify_sources else self._config.rerank_top_k,
        )
        ranked_items = (
            self._select_explicit_sources(result.items, self._config.rerank_top_k, explicit_sources)
            if diversify_sources
            else self._select_coherent_source(result.items, self._config.rerank_top_k)
        )
        # 思考内容（BE-042）：主动关闭与模型故障使用不同文案，避免把
        # RERANK_ENABLED=false 这种有意配置误报成“精排不可用”。两种状态
        # 都按 RRF 融合序输出，但只有实际异常才算 degraded。
        if result.disabled:
            emit_think(
                "evidence_ranking_node",
                f"证据按融合排序完成（精排已关闭），保留 {len(ranked_items)} 条证据",
            )
        elif result.degraded:
            emit_think(
                "evidence_ranking_node",
                f"证据重排失败，已降级为融合排序，保留 {len(ranked_items)} 条证据",
            )
        else:
            emit_think(
                "evidence_ranking_node",
                f"证据重排完成：候选 {len(pre_rerank)} 条，保留 {len(ranked_items)} 条证据",
            )
        return {
            "ranked_evidence": ranked_items,
            "rag_trace": [
                make_trace(
                    "evidence_ranking_node",
                    "success",
                    timer.elapsed_ms(),
                    extra={
                        "input_count": len(raw_candidates),
                        "dedup_count": len(candidates),
                        "pre_rerank_count": len(pre_rerank),
                        "rerank_count": len(ranked_items),
                        "explicit_source_count": len(explicit_sources),
                        "source_diversity_enabled": diversify_sources,
                        "source_coherence_enabled": ranked_items != result.items,
                        "reranker_degraded": result.degraded,
                        "reranker_disabled": result.disabled,
                    },
                )
            ],
        }

    @staticmethod
    def _source_key(item: EvidenceItem) -> str:
        """取可用于跨平台比较的文件名核心，例如“民法典”。"""
        source = str(item.get("source_name") or item.get("title") or "")
        return Path(source).stem.replace("中华人民共和国", "").strip().casefold()

    @classmethod
    def _explicit_source_keys(cls, items: list[EvidenceItem], query: str) -> set[str]:
        """只识别原问题明确点名的候选法源，避免强行塞入无关文档。"""
        normalized_query = query.casefold()
        return {
            source_key
            for item in items
            if (source_key := cls._source_key(item)) and source_key in normalized_query
        }

    @classmethod
    def _select_explicit_sources(
        cls,
        items: list[EvidenceItem],
        limit: int,
        explicit_sources: set[str],
    ) -> list[EvidenceItem]:
        """每个被点名来源先保留一条最高分证据，再按重排顺序补齐 top-k。"""
        selected: list[EvidenceItem] = []
        selected_ids: set[int] = set()
        selected_sources: set[str] = set()
        for item in items:
            source_key = cls._source_key(item)
            if source_key in explicit_sources and source_key not in selected_sources:
                selected.append(item)
                selected_ids.add(id(item))
                selected_sources.add(source_key)
        for item in items:
            if len(selected) >= limit:
                break
            if id(item) not in selected_ids:
                selected.append(item)
        return selected[:limit]

    @classmethod
    def _select_coherent_source(cls, items: list[EvidenceItem], limit: int) -> list[EvidenceItem]:
        """单一法源连续占据前两位时，丢弃后续明显偏题法源。"""
        if len(items) < 2:
            return items[:limit]
        first_source = cls._source_key(items[0])
        prefix_count = 0
        for item in items:
            if cls._source_key(item) != first_source:
                break
            prefix_count += 1
        # ponytail: 用 top-2 连续性做轻量来源一致性启发式；若未来出现大量未点名
        # 多法源问题，再升级为带 query/source 相关性的独立评分器。
        if prefix_count < 2 or not first_source:
            return items[:limit]
        coherent = [item for item in items if cls._source_key(item) == first_source]
        return coherent[:limit] or items[:limit]
