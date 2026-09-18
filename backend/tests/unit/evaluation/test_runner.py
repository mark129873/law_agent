"""BE-049 工作流结果收集与报告测试。"""

from pathlib import Path

import pytest

from app.agent.events import emit_event
from app.domain.services.qa_workflow import QaStreamEvent
from app.evaluation.dataset import load_cases
from app.evaluation.models import EvaluationCase, JudgeScore
from app.evaluation.runner import build_and_write_report, evaluate_workflow_cases


class FakeWorkflow:
    """只模拟端口输出，不触发真实模型和 Milvus。"""

    async def ainvoke(self, input: dict, **kwargs: object) -> dict:
        if input["question"].startswith("有依据"):
            emit_event(QaStreamEvent(type="status", node="rag", phase="start"))
            emit_event(QaStreamEvent(type="plan", sub_queries=("有依据",)))
            emit_event(QaStreamEvent(type="sources", sources=({"source": "法条.txt", "content": "依据"},)))
            return {
                "rag_status": "SUCCESS",
                "answer": "结论【来源：法条.txt】",
                "evidence": [{"source_name": "法条.txt", "content": "依据"}],
                "citations": [{"source_name": "法条.txt"}],
                "grounding_passed": True,
                "trace": [{"node": "rag", "duration_ms": 12}],
            }
        emit_event(QaStreamEvent(type="plan", sub_queries=("无依据",)))
        return {
            "rag_status": "LOCAL_EVIDENCE_INSUFFICIENT",
            "answer": "知识库中暂无相关依据",
            "evidence": [],
            "citations": [],
            "grounding_passed": True,
            "trace": [],
        }


class FakeJudge:
    model_name = "fake-judge"

    async def score(self, case, *, answer, evidence, citations, actual_status):
        return JudgeScore(correctness=5, completeness=4, groundedness=5, citation_accuracy=5).apply_gate(case.must_cite)


@pytest.mark.asyncio
async def test_workflow_collector_keeps_events_metrics_and_judge() -> None:
    cases = [
        EvaluationCase(
            id="ok",
            category="local_factual",
            question="有依据的问题",
            expected_status="SUCCESS",
            expected_sources=["法条.txt"],
        ),
        EvaluationCase(
            id="empty",
            category="evidence_insufficient",
            question="无依据的问题",
            expected_status="LOCAL_EVIDENCE_INSUFFICIENT",
            must_cite=False,
        ),
    ]

    results = await evaluate_workflow_cases(FakeWorkflow(), cases, FakeJudge())

    assert [item.status_match for item in results] == [True, True]
    assert results[0].event_types == ["status", "plan", "sources"]
    assert results[0].status_events[0]["node"] == "rag"
    assert results[0].metrics["retrieval_hit_at_1"] == 1.0
    assert results[0].judge is not None and results[0].judge.passed is True
    assert results[1].metrics["retrieval_empty"] is True


def test_report_writes_json_and_markdown(tmp_path: Path) -> None:
    dataset = Path(__file__).resolve().parents[2] / "evaluation" / "rag_cases.jsonl"
    report, directory = build_and_write_report([], dataset_path=str(dataset), output_root=tmp_path)

    assert report.summary["total"] == 0
    assert (directory / "report.json").is_file()
    assert (directory / "report.md").is_file()
