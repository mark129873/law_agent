"""主图结构化输出 Schema 与统一能力结果（BE-032，设计 §8/§10/§41）。

为什么用 pydantic：这是 LLM 结构化输出（LLMService.structured_invoke）
的解析与校验契约；Agent 模块不在 pydantic 禁区（domain/application
层），与 API DTO 采用同源技术选型保持一致性。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class QueryRouterOutput(BaseModel):
    """query_router_agent 的结构化输出：规范化 + 意图 + 请求类型（设计 §8.1）。"""

    normalized_query: str = Field(description="规范化后的用户问题")
    intent: Literal[
        "legal_question", "general_question", "plugin_request", "web_request", "other"
    ] = "legal_question"
    request_type: Literal["local_rag", "plugin", "web", "direct"] = "local_rag"
    extracted_conditions: dict[str, Any] = Field(
        default_factory=dict, description="提取的基础条件（金额/年限/主体等）"
    )


class OrchestratorDecision(BaseModel):
    """orchestrator_agent 的结构化决策：下一步动作（设计 §8.2）。"""

    action: Literal["local_rag", "plugin", "web_search", "direct_answer", "finish"] = "finish"
    reason: str = ""


class GroundingCheck(BaseModel):
    """grounding_checker_agent 的结构化校验结果（设计 §8.3）。"""

    passed: bool = True
    unsupported_claims: list[str] = Field(default_factory=list, description="无依据的具体结论清单")
    citation_issues: list[str] = Field(default_factory=list, description="引用与来源不一致问题")
    reason: str = ""


class CapabilityResult(BaseModel):
    """所有 Capability 的统一输出结构（设计 §10）。

    为什么统一：observation_node 只面对一种结果形状；RAG / Tavily Web /
    Plugin Stub / 直接回答的差异全部收进 status 与 metadata——
    新增 Capability 时主图路由与观察逻辑零改动（开闭原则）。
    """

    capability: str
    status: str
    content: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    """引用条目（设计 §41）：最终回答的来源溯源单元。"""

    citation_id: str
    document_id: str = ""
    chunk_id: str = ""
    title: str = ""
    source_name: str | None = None
    source_url: str | None = None
    article_number: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
