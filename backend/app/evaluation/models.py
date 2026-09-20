"""评测领域模型：数据集契约、单案例结果和最终报告。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvaluationCase(BaseModel):
    """一条可重复执行的评测问题。"""

    id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_status: str = Field(min_length=1)
    expected_sources: list[str] = Field(default_factory=list)
    expected_answer_points: list[str] = Field(default_factory=list)
    must_cite: bool = True
    use_web_search: bool = False


class JudgeScore(BaseModel):
    """LLM Judge 的结构化评分。

    ``passed`` 不直接信任模型输出，而是由评测门槛重新计算，
    防止模型在理由和布尔值不一致时误报通过。
    """

    correctness: int = Field(default=0, ge=0, le=5)
    completeness: int = Field(default=0, ge=0, le=5)
    groundedness: int = Field(default=0, ge=0, le=5)
    citation_accuracy: int = Field(default=0, ge=0, le=5)
    passed: bool = False
    issues: list[str] = Field(default_factory=list)
    reason: str = ""

    def apply_gate(self, must_cite: bool, *, status_match: bool = True) -> "JudgeScore":
        """按统一门槛生成最终 passed 标记。

        status_match 默认保持旧调用方兼容；真实评测会显式传入状态是否
        符合数据集契约，避免“回答看起来正确但工作流走错能力”被误报通过。
        """
        passed = (
            status_match
            and self.correctness >= 4
            and self.completeness >= 3
            and self.groundedness >= 4
            and (not must_cite or self.citation_accuracy >= 4)
        )
        return self.model_copy(update={"passed": passed})


class EvaluationCaseResult(BaseModel):
    """单条问题的可审计结果，保留足够信息定位失败原因。"""

    case_id: str
    category: str
    question: str
    expected_status: str
    actual_status: str = ""
    status_match: bool = False
    grounding_passed: bool | None = None
    expected_sources: list[str] = Field(default_factory=list)
    retrieved_sources: list[str] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    answer: str = ""
    event_types: list[str] = Field(default_factory=list)
    status_events: list[dict[str, Any]] = Field(default_factory=list)
    node_durations: dict[str, int] = Field(default_factory=dict)
    trace_id: str = ""
    metrics: dict[str, float | int | bool | None] = Field(default_factory=dict)
    judge: JudgeScore | None = None
    judge_error: str = ""
    duration_ms: int = 0
    completed: bool = True
    error_type: str = ""
    error_message: str = ""


class EvaluationReport(BaseModel):
    """JSON 报告的稳定外层结构。"""

    run_id: str
    created_at: str
    dataset_path: str
    dataset_sha256: str
    git_commit: str
    settings: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    cases: list[EvaluationCaseResult] = Field(default_factory=list)
