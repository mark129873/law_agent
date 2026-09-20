"""BE-049 JSONL 数据集契约测试。"""

from pathlib import Path

import pytest

from app.evaluation.dataset import dataset_sha256, load_cases


def test_repository_evaluation_dataset_is_complete_and_versioned() -> None:
    path = Path(__file__).resolve().parents[2] / "evaluation" / "rag_cases.jsonl"
    cases = load_cases(path)

    assert len(cases) == 50
    assert len({case.id for case in cases}) == 50
    assert dataset_sha256(path)
    assert {case.category for case in cases} == {
        "local_factual",
        "multi_condition",
        "evidence_insufficient",
        "capability_control",
        "adversarial",
        "direct_control",
    }

    data_source = path.parents[1] / "data_source"
    available_sources = {item.name for item in data_source.iterdir() if item.is_file()}
    expected_sources = {source for case in cases for source in case.expected_sources}
    assert expected_sources <= available_sources


def test_dataset_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(
        '{"id":"same","category":"x","question":"a","expected_status":"SUCCESS"}\n'
        '{"id":"same","category":"x","question":"b","expected_status":"SUCCESS"}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="重复 id"):
        load_cases(path)
