"""BE-049 确定性指标测试。"""

from app.evaluation.metrics import citation_metrics, retrieval_metrics
from app.evaluation.models import JudgeScore


def test_retrieval_metrics_deduplicate_chunks_and_calculate_mrr() -> None:
    evidence = [
        {"source_name": "其他法.txt", "content": "..."},
        {"source_name": "中华人民共和国专利法.txt", "content": "..."},
        {"metadata": {"filename": "中华人民共和国专利法.txt"}, "content": "..."},
    ]
    metrics = retrieval_metrics(evidence, ["中华人民共和国专利法.txt"])

    assert metrics["retrieval_hit_at_1"] == 0.0
    assert metrics["retrieval_hit_at_3"] == 1.0
    assert metrics["retrieval_recall_at_5"] == 1.0
    assert metrics["retrieval_mrr"] == 0.5
    assert metrics["retrieved_source_count"] == 2


def test_empty_expected_sources_are_measured_as_an_empty_retrieval() -> None:
    metrics = retrieval_metrics([], [])
    citations = citation_metrics([], [], must_cite=False)

    assert metrics["retrieval_empty"] is True
    assert metrics["retrieval_hit_at_5"] == 1.0
    assert metrics["retrieval_mrr"] == 1.0
    assert citations["citation_precision"] == 1.0
    assert citations["citation_recall"] == 1.0


def test_judge_pass_gate_is_recomputed_from_scores() -> None:
    score = JudgeScore(
        correctness=5,
        completeness=3,
        groundedness=4,
        citation_accuracy=2,
        passed=True,
    )

    assert score.apply_gate(must_cite=True).passed is False
    assert score.apply_gate(must_cite=False).passed is True
    assert score.apply_gate(must_cite=False, status_match=False).passed is False
