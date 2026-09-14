"""检索规划节点（BE-034，设计 §21）：分析本地检索需求，生成 Retrieval Plan。"""

from __future__ import annotations

from app.agent.subgraphs.legal_rag.config import LegalRAGConfig
from app.agent.subgraphs.legal_rag.prompts.retrieval_planner import build_planner_messages
from app.agent.subgraphs.legal_rag.schemas import RetrievalPlan
from app.agent.subgraphs.legal_rag.state import LegalRAGState
from app.agent.services.llm_service import LLMService
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer


class RetrievalPlannerAgent:
    """首轮检索计划：在四类查询变体中多选（设计 §9.1）。

    为什么规划独立成节点：查询策略决定后续 fan-out 与检索成本，
    与"执行计划"（strategy_router）分离才能各自演进；
    复杂的子查询拆分不在本层做（设计 §11.1：router 不负责 Retrieval Plan）。
    """

    def __init__(self, llm: LLMService, config: LegalRAGConfig) -> None:
        self._llm = llm
        self._config = config

    async def __call__(self, state: LegalRAGState) -> dict:
        timer = Timer()
        original = state.get("original_query") or ""
        normalized = state.get("normalized_query") or original
        # 安全默认（设计 §47）：Planner 默认只启用原始问题——解析失败也能继续检索
        plan = await self._llm.structured_invoke(
            build_planner_messages(original, normalized),
            RetrievalPlan,
            default=RetrievalPlan(),
        )
        return {
            "retrieval_plan": plan.model_dump(),
            "rag_trace": [
                make_trace(
                    "retrieval_planner_agent",
                    "success",
                    timer.elapsed_ms(),
                    extra={
                        "model": self._llm.model_name,
                        "use_original": plan.use_original_query,
                        "use_rewrite": plan.use_query_rewrite,
                        "use_subquery": plan.use_subquery,
                        "use_expansion": plan.use_query_expansion,
                    },
                )
            ],
        }
