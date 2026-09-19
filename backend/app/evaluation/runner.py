"""工作流评测运行器与 JSON/Markdown 报告输出。"""

from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from app.agent.events import event_emitter_var
from app.agent.services.llm_service import LLMService
from app.agent.trace_context import trace_span_var
from app.config.settings import Settings
from app.containers import _build_trace_sink_factory, build_evaluation_judge_provider, create_container
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.repositories.vector_store import VectorStore
from app.domain.services.qa_workflow import QaWorkflow, QaStreamEvent
from app.domain.services.trace_sink import TraceSink, trace_sink_var
from app.evaluation.dataset import dataset_sha256
from app.evaluation.judge import EvaluationJudge
from app.evaluation.metrics import citation_metrics, retrieval_metrics, source_names, summarize_results
from app.evaluation.models import EvaluationCase, EvaluationCaseResult, EvaluationReport


async def evaluate_workflow_cases(
    workflow: QaWorkflow,
    cases: list[EvaluationCase],
    judge: EvaluationJudge | None = None,
    trace_sink_factory: Callable[[], TraceSink | None] | None = None,
) -> list[EvaluationCaseResult]:
    """对任意 QaWorkflow 执行评测；可选地为每条案例建立 Langfuse trace。"""
    results: list[EvaluationCaseResult] = []
    for case in cases:
        started = perf_counter()
        events: list[QaStreamEvent] = []
        trace_sink = trace_sink_factory() if trace_sink_factory is not None else None
        trace_token = trace_sink_var.set(trace_sink) if trace_sink is not None else None
        trace_finished = False
        trace_id = ""
        try:
            if trace_sink is not None:
                trace_sink.start_trace(session_id=f"evaluation-{case.id}", question=case.question)
                trace_id = str(getattr(trace_sink, "trace_id", "") or "")

            event_token = event_emitter_var.set(events.append)
            try:
                final = await workflow.ainvoke(
                    {
                        "question": case.question,
                        "history": [],
                        "conversation_id": f"evaluation-{case.id}",
                        "web_search_requested": case.use_web_search,
                    }
                )
            except Exception as error:
                safe_error = _safe_error(error)
                if trace_sink is not None:
                    trace_sink.end_trace(
                        error=safe_error,
                        metadata={"evaluation_case_id": case.id},
                    )
                    trace_finished = True
                results.append(
                    EvaluationCaseResult(
                        case_id=case.id,
                        category=case.category,
                        question=case.question,
                        expected_status=case.expected_status,
                        expected_sources=case.expected_sources,
                        trace_id=trace_id,
                        duration_ms=_elapsed_ms(started),
                        completed=False,
                        error_type=type(error).__name__,
                        error_message=safe_error,
                    )
                )
                continue
            finally:
                event_emitter_var.reset(event_token)

            evidence = _as_dict_list(final.get("evidence") or final.get("ranked_evidence") or [])
            citations = _as_dict_list(final.get("citations") or [])
            answer = str(final.get("answer") or final.get("final_answer") or "")
            actual_status = str(final.get("rag_status") or final.get("capability_status") or "")
            grounding_passed = final.get("grounding_passed")
            grounding = grounding_passed if isinstance(grounding_passed, bool) else None
            metrics = retrieval_metrics(evidence, case.expected_sources)
            metrics.update(citation_metrics(citations, case.expected_sources, case.must_cite))
            metrics["status_match"] = actual_status == case.expected_status
            metrics["grounding_passed"] = grounding
            node_durations = _trace_durations(final.get("trace") or [])
            result = EvaluationCaseResult(
                case_id=case.id,
                category=case.category,
                question=case.question,
                expected_status=case.expected_status,
                actual_status=actual_status,
                status_match=actual_status == case.expected_status,
                grounding_passed=grounding,
                expected_sources=case.expected_sources,
                retrieved_sources=source_names(evidence),
                citations=citations,
                evidence=_compact_evidence(evidence),
                answer=answer,
                event_types=[event.type for event in events],
                status_events=[
                    {
                        "node": event.node,
                        "label": event.label,
                        "phase": event.phase,
                        "duration_ms": event.duration_ms,
                    }
                    for event in events
                    if event.type == "status"
                ],
                node_durations=node_durations,
                trace_id=trace_id,
                metrics=metrics,
                duration_ms=_elapsed_ms(started),
            )

            _record_evaluation_events(trace_sink, events, evidence)
            if judge is not None:
                judge_started = perf_counter()
                judge_span = trace_sink.start_span(node="evaluation_judge") if trace_sink else None
                judge_token = trace_span_var.set(judge_span) if judge_span is not None else None
                try:
                    result.judge = await judge.score(
                        case,
                        answer=answer,
                        evidence=result.evidence,
                        citations=citations,
                        actual_status=actual_status,
                    )
                except Exception as error:
                    # Judge 故障不能掩盖工作流结果；报告中单独记录，后续案例继续执行。
                    result.judge_error = _safe_error(error)
                finally:
                    if judge_token is not None:
                        trace_span_var.reset(judge_token)
                    if judge_span is not None:
                        judge_span.end(duration_ms=_elapsed_ms(judge_started), error=result.judge_error or None)

            if trace_sink is not None:
                trace_sink.record_event(
                    name="evaluation_result",
                    payload={
                        "case_id": case.id,
                        "expected_status": case.expected_status,
                        "actual_status": actual_status,
                        "status_match": str(result.status_match),
                        "grounding_passed": str(grounding),
                        "evidence_count": str(len(evidence)),
                        "citation_count": str(len(citations)),
                    },
                )
                if result.judge is not None:
                    trace_sink.record_event(
                        name="judge_score",
                        payload={
                            "passed": str(result.judge.passed),
                            "correctness": str(result.judge.correctness),
                            "completeness": str(result.judge.completeness),
                            "groundedness": str(result.judge.groundedness),
                            "citation_accuracy": str(result.judge.citation_accuracy),
                        },
                    )
                trace_sink.end_trace(
                    output=answer,
                    metadata={
                        "evaluation_case_id": case.id,
                        "expected_status": case.expected_status,
                        "actual_status": actual_status,
                        "status_match": str(result.status_match),
                        "grounding_passed": str(grounding),
                        "judge_passed": str(result.judge.passed if result.judge else False),
                    },
                )
                trace_finished = True
            results.append(result)
        finally:
            if trace_sink is not None and not trace_finished:
                trace_sink.end_trace(
                    error="evaluation case aborted",
                    metadata={"evaluation_case_id": case.id},
                )
            if trace_token is not None:
                trace_sink_var.reset(trace_token)
    return results


async def run_workflow_evaluation(
    cases: list[EvaluationCase],
    settings: Settings,
    *,
    dataset_path: str,
    output_root: str | Path = "log/evaluation",
) -> tuple[EvaluationReport, Path]:
    """装配真实工作流、初始化向量库并写出一份评测报告。"""
    container = create_container(settings)
    vector_store = container.resolve(VectorStore)
    await vector_store.initialize()
    trace_sink_factory = _build_trace_sink_factory(settings)
    try:
        workflow = container.resolve(QaWorkflow)
        primary = container.resolve(LLMProvider)
        judge_provider = build_evaluation_judge_provider(settings, primary)
        judge = EvaluationJudge(LLMService(judge_provider))
        results = await evaluate_workflow_cases(workflow, cases, judge, trace_sink_factory)
        settings_snapshot = _settings_snapshot(settings, primary.model_name, judge.model_name)
    finally:
        await vector_store.close()
        if trace_sink_factory is not None:
            shutdown = getattr(trace_sink_factory, "shutdown", None)
            if callable(shutdown):
                shutdown()

    report, report_dir = build_and_write_report(
        results,
        dataset_path=dataset_path,
        settings=settings_snapshot,
        output_root=output_root,
    )
    return report, report_dir


def build_and_write_report(
    results: list[EvaluationCaseResult],
    *,
    dataset_path: str,
    settings: dict[str, Any] | None = None,
    output_root: str | Path = "log/evaluation",
) -> tuple[EvaluationReport, Path]:
    """生成 JSON 和 Markdown 两种可读报告。"""
    run_id = _new_run_id()
    report = EvaluationReport(
        run_id=run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        dataset_path=str(Path(dataset_path)),
        dataset_sha256=dataset_sha256(dataset_path),
        git_commit=_git_commit(),
        settings=settings or {},
        summary=summarize_results(results),
        cases=results,
    )
    report_dir = Path(output_root) / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.json").write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (report_dir / "report.md").write_text(_render_markdown(report), encoding="utf-8")
    return report, report_dir


def _as_dict_list(items: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in items if isinstance(item, dict)]


def _compact_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """截断报告内证据正文，保留 Judge 所需上下文和来源定位字段。"""
    compact: list[dict[str, Any]] = []
    for item in evidence[:10]:
        compact.append(
            {
                "id": item.get("id") or item.get("chunk_id") or "",
                "source_name": item.get("source_name") or item.get("title") or item.get("source") or "",
                "content": str(item.get("content") or "")[:1600],
                "article_number": item.get("article_number") or "",
                "rrf_score": item.get("rrf_score") or item.get("score"),
            }
        )
    return compact


def _trace_durations(trace: Any) -> dict[str, int]:
    durations: dict[str, int] = {}
    if not isinstance(trace, list):
        return durations
    for item in trace:
        if not isinstance(item, dict) or not item.get("node"):
            continue
        duration = item.get("duration_ms")
        if isinstance(duration, (int, float)):
            durations[str(item["node"])] = int(duration)
    return durations


def _elapsed_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)


def _record_evaluation_events(
    trace_sink: TraceSink | None,
    events: list[QaStreamEvent],
    evidence: list[dict[str, Any]],
) -> None:
    """把直调评测中不会经过 ChatService 的流程事件补进 trace。"""
    if trace_sink is None:
        return
    for event in events:
        if event.type == "plan":
            trace_sink.record_event(
                name="plan",
                payload={"sub_queries": "；".join(event.sub_queries)[:1000]},
            )
        elif event.type in {"sources", "web_sources"}:
            trace_sink.record_event(
                name=event.type,
                payload={
                    "count": str(len(event.sources)),
                    "sources": "；".join(source_names(_as_dict_list(event.sources)))[:1000],
                },
            )
        elif event.type == "web_search_notice":
            trace_sink.record_event(
                name=event.type,
                payload={"code": event.code, "message": event.message[:500]},
            )
        elif event.type == "regenerating":
            trace_sink.record_event(name=event.type, payload={})
        elif event.type == "think":
            trace_sink.record_event(
                name=event.type,
                payload={"node": event.node, "text": event.text[:500]},
            )
    trace_sink.record_event(
        name="retrieval_summary",
        payload={
            "evidence_count": str(len(evidence)),
            "sources": "；".join(source_names(evidence))[:1000],
        },
    )


def _safe_error(error: Exception) -> str:
    """给报告保留排障摘要，同时删除常见密钥/Authorization 形态。"""
    message = str(error).replace("\r", " ").replace("\n", " ")[:500]
    message = re.sub(
        r"(?i)(api[-_ ]?key|authorization|token|secret)(\s*[:=]\s+)[^,; ]+",
        r"\1=<redacted>",
        message,
    )
    for value in os.environ.values():
        if value and len(value) >= 8:
            message = message.replace(value, "<redacted>")
    return message or type(error).__name__


def _settings_snapshot(settings: Settings, primary_model: str, judge_model: str) -> dict[str, Any]:
    """只写非敏感配置，API Key 仅以是否配置表示。"""
    return {
        "llm_provider": settings.llm_provider.value,
        "llm_model": primary_model,
        "embedding_model": settings.ollama_embedding_model,
        "milvus_provider": settings.milvus_provider.value,
        "milvus_uri": settings.resolved_milvus_uri,
        "milvus_collection_name": settings.milvus_collection_name,
        "rerank_enabled": settings.rerank_enabled,
        "reranker_model_path": settings.reranker_model_path,
        "eval_judge_provider": settings.eval_judge_provider.value,
        "eval_judge_model": judge_model,
        "glm_api_key_configured": bool(settings.glm_api_key),
        "deepseek_api_key_configured": bool(settings.deepseek_api_key),
    }


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _render_markdown(report: EvaluationReport) -> str:
    summary = report.summary
    lines = [
        "# RAG 评测报告",
        "",
        f"- run_id: `{report.run_id}`",
        f"- created_at: `{report.created_at}`",
        f"- dataset: `{report.dataset_path}`",
        f"- dataset_sha256: `{report.dataset_sha256}`",
        f"- git_commit: `{report.git_commit}`",
        "",
        "## 摘要",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| 案例数 | {summary.get('total', 0)} |",
        f"| 完成数 | {summary.get('completed', 0)} |",
        f"| 工作流失败数 | {summary.get('failed', 0)} |",
        f"| 状态匹配率 | {_percent(summary.get('status_match_rate'))} |",
        f"| grounding 通过率 | {_percent(summary.get('grounding_pass_rate'))} |",
        f"| Judge 通过率 | {_percent(summary.get('judge_pass_rate'))} |",
        f"| Hit@5 | {_percent(summary.get('retrieval_hit_at_5'))} |",
        f"| Recall@5 | {_percent(summary.get('retrieval_recall_at_5'))} |",
        f"| MRR | {_percent(summary.get('retrieval_mrr'))} |",
        f"| 引用精确率 | {_percent(summary.get('citation_precision'))} |",
        f"| 引用召回率 | {_percent(summary.get('citation_recall'))} |",
        f"| 延迟 P50/P95 | {summary.get('latency_ms', {}).get('p50')} / {summary.get('latency_ms', {}).get('p95')} ms |",
        "",
        "## 案例明细",
        "",
        "| ID | 类别 | 期望/实际状态 | Hit@5 | MRR | Judge | 耗时 |",
        "| --- | --- | --- | ---: | ---: | --- | ---: |",
    ]
    for item in report.cases:
        judge = "错误" if item.judge_error else ("通过" if item.judge and item.judge.passed else ("未通过" if item.judge else "-") )
        lines.append(
            f"| `{item.case_id}` | {item.category} | {item.expected_status} / {item.actual_status or '-'} | "
            f"{_percent(item.metrics.get('retrieval_hit_at_5'))} | {_percent(item.metrics.get('retrieval_mrr'))} | "
            f"{judge} | {item.duration_ms} ms |"
        )
        if item.error_message or item.judge_error or (item.judge and item.judge.issues):
            details = item.error_message or item.judge_error or "；".join(item.judge.issues)
            lines.append(f"  - 备注：{details}")
    return "\n".join(lines) + "\n"


def _percent(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.1f}%" if isinstance(value, (int, float)) and 0 <= float(value) <= 1 else str(value)
