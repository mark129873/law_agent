"""Local Legal RAG 子图状态与证据条目（BE-032，设计 §7 经并行安全适配）。

为什么多个列表通道用 Annotated[list, operator.add] 归约器：
strategy_router_node 的多选策略会 fan-out 并行执行多个查询变体节点
（设计约束 15/17），并行写同一通道必须配归约器，否则触发 LangGraph
的 InvalidUpdateError（Session 028 已踩坑）；追加语义同时天然支持
Recovery 多轮累积（第二轮在第一轮结果之上继续追加）。

为什么内部 trace 命名为 rag_trace 而不是 trace：子图作为编译图节点
接入主图时，LangGraph 按同名通道传入/回传状态——若同名，父图的
既有 trace 会与子图内部值互相覆盖或重复追加；独立命名让子图 trace
只留在子图作用域（经 ainvoke 结果与日志观测），主图 trace 不被污染。
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class EvidenceItem(TypedDict, total=False):
    """证据条目（设计 §7）：混合检索候选归一后的最小证据单元。

    为什么分数拆四个字段：dense/bm25 分数一期由 Milvus 服务端融合
    不可见（rrf_score 承载融合结果），rerank_score 由
    evidence_ranking_node 统一填写——字段预留使二期把两路原始分
    透出时无需改状态结构。
    """

    id: str
    document_id: str
    chunk_id: str

    title: str
    content: str

    query: str       # 命中该证据的检索查询
    query_type: str  # original / rewrite / subquery / expansion

    dense_score: float
    bm25_score: float
    rrf_score: float      # Milvus 服务端 RRF 融合分（越大越相关）
    rerank_score: float   # 统一 rerank 分（evidence_ranking_node 填写）

    source_name: str
    source_type: str
    source_url: str

    metadata: dict[str, Any]
    matched_queries: list[str]  # 多 Query 命中同一 chunk 的合并记录（设计 §33）


class LegalRAGState(TypedDict, total=False):
    # ---- 输入（主图经同名通道传入）----
    original_query: str
    normalized_query: str

    # ---- 规划 ----
    retrieval_plan: dict[str, Any]   # 首轮检索计划（retrieval_planner_agent 产出）
    recovery_plan: dict[str, Any]    # 恢复计划（recovery_planner_agent 产出）
    current_plan: dict[str, Any]     # 当前生效计划（strategy_router_node 统一，设计 §22）

    # ---- 查询变体（fan-out 并行追加 + Recovery 多轮累积）----
    rewritten_queries: Annotated[list[str], operator.add]
    sub_queries: Annotated[list[str], operator.add]
    expanded_queries: Annotated[list[str], operator.add]
    retrieval_queries: list[dict[str, str]]  # 本轮实际检索的查询（hybrid_retriever 汇总）

    # ---- 检索 ----
    retrieval_candidates: Annotated[list[EvidenceItem], operator.add]
    retrieved_query_texts: list[str]  # 已检索过的查询文本（恢复轮排除重复检索）
    retrieval_error: str  # 检索通道故障描述（空串=正常；rag_result 据此输出 RETRIEVAL_ERROR）

    # ---- 证据 ----
    ranked_evidence: list[EvidenceItem]

    evidence_sufficient: bool
    evidence_confidence: float
    missing_evidence: list[str]
    evidence_conflicts: list[str]
    local_recovery_possible: bool

    # ---- Retry（设计 §37）----
    retry_count: int
    max_retries: int

    # ---- 结果（设计 §38）----
    rag_status: str
    suggested_external_queries: list[str]

    # ---- Trace（子图作用域，追加语义）----
    rag_trace: Annotated[list[dict[str, Any]], operator.add]
