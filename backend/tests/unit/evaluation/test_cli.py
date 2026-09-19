"""评测 CLI 回归：数据准备和质量评测仍可运行，已移除的入口明确报错。"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts.evaluate_rag import _run, build_parser


def test_removed_command_is_rejected(capsys) -> None:
    """防止旧命令悄悄落到其他分支，意外执行数据导入或模型调用。"""
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(["api-smoke"])

    assert error.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_prepare_dispatch_keeps_reset_explicit(tmp_path, monkeypatch) -> None:
    """以异步替身隔离 HTTP，验证模块迁移后仍能默认追加导入并写报告。"""
    prepare = AsyncMock(return_value={"uploaded": [{"id": "document-1"}]})
    monkeypatch.setattr("app.evaluation.corpus.prepare_corpus", prepare)
    args = build_parser().parse_args(["prepare", "--output-root", str(tmp_path)])

    assert args.reset is False
    assert build_parser().parse_args(["prepare", "--reset"]).reset is True
    assert await _run(args) == 0
    prepare.assert_awaited_once_with("http://127.0.0.1:8000", reset=False)
    report_path, = tmp_path.glob("prepare-*/prepare.json")
    assert json.loads(report_path.read_text(encoding="utf-8"))["uploaded"] == [{"id": "document-1"}]


@pytest.mark.asyncio
async def test_workflow_dispatch_loads_dataset_and_runs_quality_evaluation(tmp_path, monkeypatch) -> None:
    """复用真实数据集解析，只替换外部工作流执行，避免回归测试触发模型计费。"""
    dataset = Path(__file__).resolve().parents[2] / "evaluation" / "rag_cases.jsonl"
    evaluate = AsyncMock(return_value=(SimpleNamespace(summary={"total": 23}), tmp_path))
    monkeypatch.setattr("app.evaluation.runner.run_workflow_evaluation", evaluate)
    args = build_parser().parse_args([
        "workflow", "--cases", str(dataset), "--output-root", str(tmp_path),
    ])

    assert await _run(args) == 0
    evaluate.assert_awaited_once()
    call = evaluate.await_args
    assert len(call.args[0]) == 23
    assert call.kwargs == {"dataset_path": str(dataset), "output_root": str(tmp_path)}
