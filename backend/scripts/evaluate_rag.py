"""RAG 评测 CLI。

入口保持薄：数据集、工作流、HTTP 冒烟分别由 app.evaluation 模块负责，
脚本只处理参数、运行配置和退出码。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="法律 RAG 端到端评测")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="清理评测库并通过 HTTP 导入测试文档")
    prepare.add_argument("--base-url", default="http://127.0.0.1:8000")
    prepare.add_argument("--reset-eval", action="store_true", help="删除当前评测数据库中的已有文档")
    prepare.add_argument("--output-root", default="log/evaluation")

    workflow = subparsers.add_parser("workflow", help="直接调用 QaWorkflow 执行完整评测")
    workflow.add_argument("--cases", default="tests/evaluation/rag_cases.jsonl")
    workflow.add_argument("--collection", default="", help="评测 Milvus 集合名，必须以 law_agent_eval 开头")
    workflow.add_argument("--output-root", default="log/evaluation")

    smoke = subparsers.add_parser("api-smoke", help="通过 HTTP/SSE 验证产品链路")
    smoke.add_argument("--base-url", default="http://127.0.0.1:8000")
    smoke.add_argument("--cases", default="tests/evaluation/rag_cases.jsonl")
    smoke.add_argument("--output-root", default="log/evaluation")
    return parser


async def _run(args: argparse.Namespace) -> int:
    from app.evaluation.dataset import load_cases
    from app.evaluation.http_smoke import prepare_corpus, run_api_smoke

    if args.command == "prepare":
        _load_eval_collection_into_env()
        result = await prepare_corpus(args.base_url, reset_eval=args.reset_eval)
        output_dir = _new_output_dir(args.output_root, "prepare")
        (output_dir / "prepare.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"passed": True, "report_dir": str(output_dir), **result}, ensure_ascii=False))
        return 0

    cases = load_cases(args.cases)
    if args.command == "workflow":
        from app.config.settings import Settings
        from app.evaluation.runner import run_workflow_evaluation

        settings = Settings()
        collection = args.collection or settings.milvus_collection_name
        if not collection.startswith("law_agent_eval"):
            raise RuntimeError("workflow 评测要求独立集合名，以 law_agent_eval 开头。")
        settings = settings.model_copy(update={"milvus_collection_name": collection})
        report, report_dir = await run_workflow_evaluation(
            cases,
            settings,
            dataset_path=args.cases,
            output_root=args.output_root,
        )
        print(json.dumps({"passed": True, "report_dir": str(report_dir), "summary": report.summary}, ensure_ascii=False))
        return 0

    if args.command == "api-smoke":
        _load_eval_collection_into_env()
        result = await run_api_smoke(args.base_url, cases)
        output_dir = _new_output_dir(args.output_root, "api-smoke")
        (output_dir / "api-smoke.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / "api-smoke.md").write_text(_render_smoke_markdown(result), encoding="utf-8")
        print(json.dumps({"report_dir": str(output_dir), **result}, ensure_ascii=False))
        return 0 if result["passed"] else 1

    raise AssertionError(f"未知命令：{args.command}")


def _load_eval_collection_into_env() -> str:
    """读取 backend/.env 后同步到当前进程，供安全检查使用。"""
    from app.config.settings import Settings

    settings = Settings()
    collection = os.environ.get("MILVUS_COLLECTION_NAME") or settings.milvus_collection_name
    os.environ.setdefault("MILVUS_COLLECTION_NAME", collection)
    return collection


def _new_output_dir(root: str, prefix: str) -> Path:
    run_id = f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    path = Path(root) / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _render_smoke_markdown(result: dict) -> str:
    lines = ["# API/SSE 冒烟结果", "", f"- base_url: `{result['base_url']}`", f"- passed: `{result['passed']}`", ""]
    for case in result["cases"]:
        lines.extend([f"## {case['case_id']}", "", f"- passed: `{case['passed']}`", f"- events: `{', '.join(case['event_types'])}`", ""])
        for name, value in case["checks"].items():
            lines.append(f"- {name}: `{value}`")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    try:
        return asyncio.run(_run(build_parser().parse_args()))
    except Exception as error:
        print(f"评测失败：{type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

