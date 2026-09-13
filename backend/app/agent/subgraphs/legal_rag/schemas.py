"""Local Legal RAG 子图结构化输出 Schema（BE-032，设计 §9）。

与主图 schemas.py 同一约定：pydantic 模型作为 LLM 结构化输出的
解析与校验契约，由 LLMService.structured_invoke 消费。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RetrievalPlan(BaseModel):
    """检索计划（设计 §9.1）：多选而非单选——可同时启用多种查询变体。"""

    use_original_query: bool = True
    use_query_rewrite: bool = False
    use_subquery: bool = False
    use_query_expansion: bool = False

    target_evidence: list[str] = Field(
        default_factory=list, description="需要查找的证据主题（供 grader 对照覆盖度）"
    )
    reason: str = ""


class EvidenceGrade(BaseModel):
    """证据评估（设计 §9.2）：evidence_grader_agent 的结构化输出。

    为什么 grader 默认值不放"充分"：LLM 结构化解析失败时
    LLMService 会用安全默认（设计 §47——宁可多检索不可漏依据），
    本模型的字段默认仅用于合法但缺失字段的兜底。
    """

    sufficient: bool = False
    confidence: float = 0.0
    local_recovery_possible: bool = False
    missing_evidence: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    suggested_external_queries: list[str] = Field(
        default_factory=list, description="本地证据不足时建议的外部检索词（一期仅透传，不使用）"
    )
    reason: str = ""


class RecoveryPlan(BaseModel):
    """恢复计划（设计 §9.3）：可用动作只有本地查询变体（设计 §36）。"""

    actions: list[Literal["query_rewrite", "subquery", "query_expansion"]] = Field(
        default_factory=list
    )
    reason: str = ""
    missing_evidence: list[str] = Field(default_factory=list)
