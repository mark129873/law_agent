"""子图结果节点（BE-034，设计 §38/§46.2）：统一出口与 sources 事件。"""

from __future__ import annotations

from app.agent.constants import (
    RAG_STATUS_LOCAL_EVIDENCE_INSUFFICIENT,
    RAG_STATUS_RETRIEVAL_ERROR,
    RAG_STATUS_SUCCESS,
)
from app.agent.events import emit_event
from app.agent.subgraphs.legal_rag.state import LegalRAGState
from app.agent.utils.evidence_utils import evidence_to_source
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer
from app.domain.services.qa_workflow import QaStreamEvent


class RagResultNode:
    """据状态决定最终 rag_status（SUCCESS / LOCAL_EVIDENCE_INSUFFICIENT / RETRIEVAL_ERROR）。

    为什么 sources 事件在本节点推送而不是检索/重排节点：sources 是
    "本轮最终采用的证据"（FE-011 参考文档展示的唯一事实来源），
    只有到达出口才能确认"这批证据不再被恢复轮替换"——重规划后
    以最新一批为准的契约（ARCHITECTURE §7）由此天然成立。
    完全无命中不推送（PRODUCT.md：无命中不显示参考文档）。
    """

    async def __call__(self, state: LegalRAGState) -> dict:
        timer = Timer()
        evidence = list(state.get("ranked_evidence") or [])
        if state.get("retrieval_error"):
            status = RAG_STATUS_RETRIEVAL_ERROR
        elif state.get("evidence_sufficient"):
            status = RAG_STATUS_SUCCESS
        else:
            status = RAG_STATUS_LOCAL_EVIDENCE_INSUFFICIENT
        # 检索故障不推送证据（没有可靠依据可展示）；部分证据 + 不足 →
        # 正常推送（主图 answer_generator 据此谨慎回答并展示参考文档）
        if evidence and status != RAG_STATUS_RETRIEVAL_ERROR:
            emit_event(
                QaStreamEvent(
                    type="sources",
                    sources=tuple(evidence_to_source(item) for item in evidence),
                )
            )
        return {
            "rag_status": status,
            "rag_trace": [
                make_trace(
                    "rag_result_node",
                    "success",
                    timer.elapsed_ms(),
                    extra={"status": status, "evidence_count": len(evidence)},
                )
            ],
        }
