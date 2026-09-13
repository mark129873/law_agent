"""混合检索节点（BE-034，设计 §27/§28/§30/§31）——一期 RAG 的核心节点。

为什么 Dense+BM25+RRF 合并在一个节点（约束 11）：三者属于同一个
检索 Stage，且 Milvus 在服务端一次 hybrid_search 完成融合（BE-029），
拆成三个 LangGraph 节点只会增加状态搬运，不增加能力。
"""

from __future__ import annotations

import asyncio
import logging

from app.agent.events import emit_event
from app.agent.services.milvus_service import MilvusService
from app.agent.subgraphs.legal_rag.config import LegalRAGConfig
from app.agent.subgraphs.legal_rag.state import EvidenceItem, LegalRAGState
from app.agent.utils.evidence_utils import chunk_to_evidence
from app.agent.utils.query_utils import collect_retrieval_queries
from app.agent.utils.think_utils import emit_think
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer
from app.domain.services.qa_workflow import QaStreamEvent

logger = logging.getLogger("app.agent.subgraphs.legal_rag.retriever")

# 单查询失败后的节点内重试次数（设计 §47：允许 1 次，不无限 loop）
_SEARCH_RETRIES = 1


class HybridRetrieverNode:
    """多 Query 并发混合检索：每个查询独立走完整 Dense+BM25+RRF（设计 §28）。

    为什么"不是 SubQuery1→BM25、SubQuery2→Dense"：单通道检索会漏召回，
    所有 Query 默认走完整混合检索；查询变体的差异体现在"检索什么"，
    不在"怎么检索"。
    """

    def __init__(self, milvus: MilvusService, config: LegalRAGConfig) -> None:
        self._milvus = milvus
        self._config = config

    async def __call__(self, state: LegalRAGState) -> dict:
        timer = Timer()
        original = state.get("normalized_query") or state.get("original_query") or ""
        plan = state.get("current_plan") or {}
        queries = collect_retrieval_queries(
            base_query=original,
            rewritten_queries=list(state.get("rewritten_queries") or []),
            sub_queries=list(state.get("sub_queries") or []),
            expanded_queries=list(state.get("expanded_queries") or []),
            include_original=bool(plan.get("use_original_query", True)),
            exclude_texts=set(state.get("retrieved_query_texts") or []),
            max_queries=self._config.max_retrieval_queries,
        )
        if not queries:
            # 全部查询都已检索过（恢复轮排除后无新增）——不再重复检索
            emit_think("hybrid_retriever_node", "本轮无新增查询（均已检索过），跳过重复检索")
            return {
                "rag_trace": [
                    make_trace("hybrid_retriever_node", "success", timer.elapsed_ms(),
                               extra={"query_count": 0, "candidate_count": 0})
                ]
            }

        # 检索策略事件（D1）：每轮检索前推送本轮全部查询，重规划后覆盖前端列表
        emit_event(QaStreamEvent(type="plan", sub_queries=tuple(q["query"] for q in queries)))

        # 多 Query 并发召回（设计 §30）：避免 Q1→等→Q2→等→Q3 的串行延迟
        outcomes = await asyncio.gather(*[self._search_one(query) for query in queries])
        candidates: list[EvidenceItem] = [item for outcome in outcomes for item in outcome["items"]]
        failed = [outcome["query"] for outcome in outcomes if outcome["failed"]]

        update: dict = {
            "retrieval_queries": queries,
            "retrieval_candidates": candidates,
            "retrieved_query_texts": [query["query"] for query in queries],
            "rag_trace": [
                make_trace(
                    "hybrid_retriever_node",
                    "success",
                    timer.elapsed_ms(),
                    extra={
                        "query_count": len(queries),
                        "candidate_count": len(candidates),
                        "failed_query_count": len(failed),
                    },
                )
            ],
        }
        if failed and not candidates:
            # 全部查询失败（各重试 1 次后）→ 检索通道故障（设计 §47：返回错误而非无限重试）
            emit_think("hybrid_retriever_node", f"检索故障：全部 {len(queries)} 条查询失败")
            update["retrieval_error"] = f"hybrid search failed for all {len(queries)} queries"
            logger.error(
                "Agent hybrid retrieval failed for all queries",
                extra={"service": "agent", "query_count": len(queries), "failed": failed},
            )
        else:
            # 思考内容（BE-042）：运行细节——查询数/命中数/失败数一行汇总
            failed_note = f"，{len(failed)} 条查询失败" if failed else ""
            emit_think(
                "hybrid_retriever_node",
                f"并发检索 {len(queries)} 条查询，命中 {len(candidates)} 条候选{failed_note}",
            )
        return update

    async def _search_one(self, query: dict[str, str]) -> dict:
        """单查询检索 + 节点内重试 1 次（设计 §47）；最终失败返回空并标记。"""
        last_error: Exception | None = None
        for _ in range(_SEARCH_RETRIES + 1):
            try:
                chunks = await self._milvus.hybrid_search(
                    query["query"], top_k=self._config.hybrid_top_k
                )
                return {
                    "items": [
                        chunk_to_evidence(chunk, query["query"], query["query_type"])
                        for chunk in chunks
                    ],
                    "failed": False,
                    "query": query["query"],
                }
            except Exception as error:  # noqa: BLE001——单查询故障不拖垮其他并发查询
                last_error = error
                logger.warning(
                    "Agent hybrid search attempt failed",
                    extra={
                        "service": "agent",
                        "query_type": query["query_type"],
                        "attempt_error": str(error),
                    },
                )
        return {"items": [], "failed": True, "query": query["query"], "error": str(last_error)}
