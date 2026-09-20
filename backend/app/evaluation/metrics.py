"""RAG 评测的确定性指标。

指标只依赖工作流产出的来源文件名与引用，不调用模型，因此可以用
纯 fake 工作流稳定测试；语义质量交给独立 Judge。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import mean
from typing import Any


def _name(item: Mapping[str, Any] | Any) -> str:
    """从证据或引用兼容字段中取来源文件名。"""
    if not isinstance(item, Mapping):
        return ""
    metadata = item.get("metadata")
    value = item.get("source_name") or item.get("source") or item.get("title")
    if not value and isinstance(metadata, Mapping):
        value = metadata.get("filename") or metadata.get("source")
    return Path(str(value or "")).name.strip().lower()


def source_names(items: Sequence[Mapping[str, Any] | Any]) -> list[str]:
    """按排名去重来源名，避免同一文件多个 chunk 放大召回率。"""
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        name = _name(item)
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _hit_at_k(ranked: list[str], expected: set[str], k: int) -> float:
    if not expected:
        return 1.0 if not ranked else 0.0
    return float(bool(set(ranked[:k]) & expected))


def retrieval_metrics(evidence: Sequence[Mapping[str, Any] | Any], expected_sources: Sequence[str]) -> dict[str, float | int | bool | None]:
    """计算 Hit/Recall@K 和 MRR；expected_sources 为空表示期望无本地证据。"""
    ranked = source_names(evidence)
    expected = {Path(str(item)).name.strip().lower() for item in expected_sources if str(item).strip()}
    overlap = set(ranked) & expected
    metrics: dict[str, float | int | bool | None] = {
        "retrieval_expected_empty": not expected,
        "retrieval_empty": not ranked,
        "retrieval_hit_at_1": _hit_at_k(ranked, expected, 1),
        "retrieval_hit_at_3": _hit_at_k(ranked, expected, 3),
        "retrieval_hit_at_5": _hit_at_k(ranked, expected, 5),
        "retrieval_hit_at_10": _hit_at_k(ranked, expected, 10),
        "retrieval_recall_at_1": _recall(ranked[:1], expected),
        "retrieval_recall_at_3": _recall(ranked[:3], expected),
        "retrieval_recall_at_5": _recall(ranked[:5], expected),
        "retrieval_recall_at_10": _recall(ranked[:10], expected),
        "retrieval_mrr": _mrr(ranked, expected),
        "retrieved_source_count": len(ranked),
        "expected_source_count": len(expected),
        "matched_source_count": len(overlap),
    }
    return metrics


def _recall(ranked: Sequence[str], expected: set[str]) -> float:
    if not expected:
        return 1.0 if not ranked else 0.0
    return len(set(ranked) & expected) / len(expected)


def _mrr(ranked: Sequence[str], expected: set[str]) -> float:
    if not expected:
        return 1.0 if not ranked else 0.0
    for index, name in enumerate(ranked, 1):
        if name in expected:
            return 1.0 / index
    return 0.0


def citation_metrics(
    citations: Sequence[Mapping[str, Any] | Any],
    expected_sources: Sequence[str],
    must_cite: bool,
) -> dict[str, float | int | bool | None]:
    """计算引用精确率/召回率；无引用要求时不让它成为质量门槛。"""
    actual = source_names(citations)
    expected = {Path(str(item)).name.strip().lower() for item in expected_sources if str(item).strip()}
    matched = len(set(actual) & expected)
    precision = matched / len(actual) if actual else (1.0 if not must_cite else 0.0)
    recall = matched / len(expected) if expected else (1.0 if not actual else 0.0)
    return {
        "citation_precision": precision,
        "citation_recall": recall,
        "citation_count": len(actual),
        "citation_matched_count": matched,
        "citation_required": must_cite,
    }


def summarize_results(results: Sequence[Any]) -> dict[str, Any]:
    """聚合报告摘要，跳过失败案例和缺失 Judge 的空值。"""
    completed = [item for item in results if item.completed]

    def average_metric(key: str) -> float | None:
        values = [item.metrics.get(key) for item in completed]
        numbers = [float(value) for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
        return round(mean(numbers), 4) if numbers else None

    def rate(values: Sequence[bool | None]) -> float | None:
        usable = [value for value in values if value is not None]
        return round(sum(1 for value in usable if value) / len(usable), 4) if usable else None

    latencies = sorted(int(item.duration_ms) for item in completed)
    judges = [item.judge for item in completed if item.judge is not None]
    return {
        "total": len(results),
        "completed": len(completed),
        "failed": len(results) - len(completed),
        "status_match_rate": rate([item.status_match for item in completed]),
        "grounding_pass_rate": rate([item.grounding_passed for item in completed]),
        "judge_pass_rate": rate([judge.passed for judge in judges]),
        "judge_count": len(judges),
        "judge_correctness_avg": round(mean([judge.correctness for judge in judges]), 4) if judges else None,
        "judge_completeness_avg": round(mean([judge.completeness for judge in judges]), 4) if judges else None,
        "judge_groundedness_avg": round(mean([judge.groundedness for judge in judges]), 4) if judges else None,
        "judge_citation_accuracy_avg": round(mean([judge.citation_accuracy for judge in judges]), 4) if judges else None,
        "retrieval_hit_at_1": average_metric("retrieval_hit_at_1"),
        "retrieval_hit_at_3": average_metric("retrieval_hit_at_3"),
        "retrieval_hit_at_5": average_metric("retrieval_hit_at_5"),
        "retrieval_hit_at_10": average_metric("retrieval_hit_at_10"),
        "retrieval_recall_at_5": average_metric("retrieval_recall_at_5"),
        "retrieval_mrr": average_metric("retrieval_mrr"),
        "citation_precision": average_metric("citation_precision"),
        "citation_recall": average_metric("citation_recall"),
        "latency_ms": {
            "mean": round(mean(latencies), 2) if latencies else None,
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
        },
    }


def _percentile(values: Sequence[int], ratio: float) -> int | None:
    if not values:
        return None
    index = min(len(values) - 1, max(0, math.ceil(len(values) * ratio) - 1))
    return values[index]

