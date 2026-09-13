"""证据评估节点（BE-034，设计 §35）：判断本地证据是否足以回答。

为什么必须独立于 evidence_ranking_node（约束 13）：两者职责不同——
Ranking 回答"哪些证据更相关"（排序问题），Grading 回答"这些证据
够不够回答"（覆盖度/冲突判断，需要语义理解）；合并把两种性质
不同的判断塞进一个节点，必然削弱其一。
"""

from __future__ import annotations

from app.agent.services.llm_service import LLMService
from app.agent.subgraphs.legal_rag.config import LegalRAGConfig
from app.agent.subgraphs.legal_rag.prompts.evidence_grader import build_grader_messages
from app.agent.subgraphs.legal_rag.schemas import EvidenceGrade
from app.agent.subgraphs.legal_rag.state import LegalRAGState
from app.agent.utils.evidence_utils import format_evidence_context
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer


class EvidenceGraderAgent:
    """覆盖度 / 缺失证据 / 冲突 / 本地可恢复性评估（设计 §35）。"""

    def __init__(self, llm: LLMService, config: LegalRAGConfig) -> None:
        self._llm = llm
        self._config = config

    async def __call__(self, state: LegalRAGState) -> dict:
        timer = Timer()
        evidence = list(state.get("ranked_evidence") or [])
        original = state.get("original_query") or state.get("normalized_query") or ""
        plan = state.get("current_plan") or {}
        retry = int(state.get("retry_count") or 0)
        # 安全默认（设计 §47）：Grader 默认"不充分"——宁可多检索不可误判证据充分；
        # 预算内默认允许本地恢复，给恢复循环一次机会
        default = EvidenceGrade(
            sufficient=False,
            confidence=0.0,
            local_recovery_possible=retry < self._config.max_retries,
        )
        grade = await self._llm.structured_invoke(
            build_grader_messages(
                original,
                format_evidence_context(evidence),
                list(plan.get("target_evidence") or []),
            ),
            EvidenceGrade,
            default=default,
        )
        return {
            "evidence_sufficient": grade.sufficient,
            "evidence_confidence": grade.confidence,
            "missing_evidence": grade.missing_evidence,
            "evidence_conflicts": grade.conflicts,
            "local_recovery_possible": grade.local_recovery_possible,
            "suggested_external_queries": grade.suggested_external_queries,
            "rag_trace": [
                make_trace(
                    "evidence_grader_agent",
                    "success",
                    timer.elapsed_ms(),
                    extra={
                        "model": self._llm.model_name,
                        "evidence_count": len(evidence),
                        "sufficient": grade.sufficient,
                        "confidence": grade.confidence,
                        "missing_count": len(grade.missing_evidence),
                    },
                )
            ],
        }
