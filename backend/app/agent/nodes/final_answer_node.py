"""最终回答节点（BE-036，设计 §20）：确定性收尾，不再做推理。

负责：Citation 编号与去重、端口输出键（answer）回填、trace 收尾。
"""

from __future__ import annotations

from app.agent.schemas import Citation
from app.agent.services.citation_service import CitationService
from app.agent.state import AgentState
from app.agent.subgraphs.legal_rag.state import EvidenceItem
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer


class FinalAnswerNode:
    """整理 Citation 与输出结构（Markdown 已由生成节点产出）。"""

    def __init__(self, citation_service: CitationService) -> None:
        self._citations = citation_service

    async def __call__(self, state: AgentState) -> dict:
        timer = Timer()
        answer_draft = state.get("answer_draft") or ""
        evidence = list(state.get("evidence") or [])
        citations = [c.model_dump() for c in self._citations.build_citations(
            [EvidenceItem(item) for item in evidence]
        )]
        return {
            "final_answer": answer_draft,
            "answer": answer_draft,  # QaWorkflow 端口输出键（ChatService/run_qa 消费）
            "citations": citations,
            "trace": [
                make_trace(
                    "final_answer_node",
                    "success",
                    timer.elapsed_ms(),
                    extra={"answer_length": len(answer_draft), "citation_count": len(citations)},
                )
            ],
        }
