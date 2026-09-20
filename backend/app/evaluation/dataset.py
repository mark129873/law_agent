"""JSONL 评测数据集的读取与校验。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.evaluation.models import EvaluationCase


def load_cases(path: str | Path) -> list[EvaluationCase]:
    """读取 JSONL，并在进入真实模型前拒绝空问题、重复 id 和坏 JSON。"""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"评测数据集不存在：{file_path}")

    cases: list[EvaluationCase] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as error:
            raise ValueError(f"评测数据集第 {line_number} 行不是合法 JSON：{error.msg}") from error
        try:
            case = EvaluationCase.model_validate(payload)
        except Exception as error:
            raise ValueError(f"评测数据集第 {line_number} 行契约校验失败：{error}") from error
        if case.id in seen_ids:
            raise ValueError(f"评测数据集存在重复 id：{case.id}")
        seen_ids.add(case.id)
        cases.append(case)

    if not cases:
        raise ValueError(f"评测数据集为空：{file_path}")
    return cases


def dataset_sha256(path: str | Path) -> str:
    """返回数据集原始字节摘要，报告用它标识本次输入版本。"""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

