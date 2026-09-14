"""观察节点（BE-036，设计 §14）：统一 Capability Result 到全局状态。

确定性节点：不生成自然语言，只做结构归并——保存能力名与状态、
合并证据引用、步数 +1、写 trace。
"""

from __future__ import annotations

from app.agent.constants import (
    CAPABILITY_DISABLED,
    CAPABILITY_LOCAL_EVIDENCE_INSUFFICIENT,
    CAPABILITY_NOT_IMPLEMENTED,
    CAPABILITY_RETRIEVAL_ERROR,
    RAG_STATUS_LOCAL_EVIDENCE_INSUFFICIENT,
    RAG_STATUS_RETRIEVAL_ERROR,
    RAG_STATUS_SUCCESS,
)
from app.agent.schemas import CapabilityResult
from app.agent.state import AgentState
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer

# RAG 子图状态 → Capability 统一状态（设计 §10 的映射）
_RAG_STATUS_TO_CAPABILITY = {
    RAG_STATUS_SUCCESS: "SUCCESS",
    RAG_STATUS_LOCAL_EVIDENCE_INSUFFICIENT: CAPABILITY_LOCAL_EVIDENCE_INSUFFICIENT,
    RAG_STATUS_RETRIEVAL_ERROR: CAPABILITY_RETRIEVAL_ERROR,
}


def _capability_result_for(state: AgentState) -> CapabilityResult:
    """按最近能力归一结果：RAG 从子图回写键构造，其余能力读 capability_result。"""
    capability = state.get("last_capability") or ""
    if capability == "local_rag":
        rag_status = state.get("rag_status") or RAG_STATUS_RETRIEVAL_ERROR
        return CapabilityResult(
            capability="local_legal_rag",
            status=_RAG_STATUS_TO_CAPABILITY.get(rag_status, CAPABILITY_RETRIEVAL_ERROR),
            evidence=list(state.get("ranked_evidence") or []),
            metadata={
                "missing_evidence": list(state.get("missing_evidence") or []),
                "suggested_external_queries": list(state.get("suggested_external_queries") or []),
            },
        )
    raw = state.get("capability_result") or {}
    return CapabilityResult(
        capability=str(raw.get("capability") or capability or "unknown"),
        status=str(raw.get("status") or CAPABILITY_DISABLED),
        content=raw.get("content"),
        evidence=list(raw.get("evidence") or []),
        citations=list(raw.get("citations") or []),
        metadata=dict(raw.get("metadata") or {}),
    )


class ObservationNode:
    """统一 Capability Result：Content / Evidence / Metadata → 全局状态。"""

    async def __call__(self, state: AgentState) -> dict:
        timer = Timer()
        result = _capability_result_for(state)
        # 为什么证据用"latest wins"而不是跨能力累加（设计 §14 的"合并"
        # 按归一合并实现）：一期单轮只会有一份有效证据（RAG 或直接回答），
        # 累加旧能力残留证据会让 grounding 与参考文档展示口径漂移。
        step_count = int(state.get("global_step_count") or 0) + 1
        return {
            "last_capability": result.capability,
            "capability_status": result.status,
            "capability_result": result.model_dump(),
            "evidence": result.evidence,
            "citations": result.citations,
            "global_step_count": step_count,
            "trace": [
                make_trace(
                    "observation_node",
                    "success",
                    timer.elapsed_ms(),
                    extra={
                        "capability": result.capability,
                        "status": result.status,
                        "evidence_count": len(result.evidence),
                        "global_step_count": step_count,
                    },
                )
            ],
        }
