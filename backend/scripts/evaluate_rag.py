"""RAG 评测 CLI。

入口保持薄：数据集、文档导入、工作流评测分别由 app.evaluation 模块负责，
脚本只处理参数、运行配置和退出码。真实 workflow 评测固定使用
DeepSeek + Milvus + llama serve Qwen3 Embedding/Reranker。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="法律 RAG 生成质量评测")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="向当前知识库导入测试文档")
    prepare.add_argument("--base-url", default="http://127.0.0.1:8000")
    prepare.add_argument("--reset", action="store_true", help="危险：删除当前数据库中的全部文档后再导入测试文档")
    prepare.add_argument("--output-root", default="log/evaluation")

    workflow = subparsers.add_parser(
        "workflow",
        help="使用 DeepSeek + Milvus + llama serve Qwen3 Embedding/Reranker 直接调用 QaWorkflow 执行评测",
    )
    workflow.add_argument("--cases", default="tests/evaluation/rag_cases.jsonl")
    workflow.add_argument("--output-root", default="log/evaluation")

    return parser


async def _run(args: argparse.Namespace) -> int:
    from app.evaluation.dataset import load_cases

    if args.command == "prepare":
        from app.evaluation.corpus import prepare_corpus

        result = await prepare_corpus(args.base_url, reset=args.reset)
        output_dir = _new_output_dir(args.output_root, "prepare")
        (output_dir / "prepare.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"passed": True, "report_dir": str(output_dir), **result}, ensure_ascii=False))
        return 0

    cases = load_cases(args.cases)
    if args.command == "workflow":
        from app.config.settings import Settings
        from app.evaluation.runner import run_workflow_evaluation

        settings = Settings()
        report, report_dir = await run_workflow_evaluation(
            cases,
            settings,
            dataset_path=args.cases,
            output_root=args.output_root,
        )
        print(json.dumps({"passed": True, "report_dir": str(report_dir), "summary": report.summary}, ensure_ascii=False))
        return 0

    raise AssertionError(f"未知命令：{args.command}")


def _new_output_dir(root: str, prefix: str) -> Path:
    run_id = f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    path = Path(root) / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def main() -> int:
    try:
        return asyncio.run(_run(build_parser().parse_args()))
    except Exception as error:
        print(f"评测失败：{type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
