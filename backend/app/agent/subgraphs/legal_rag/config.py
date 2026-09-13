"""Local Legal RAG 子图配置（BE-032，设计 §43）。

默认值与设计文档对齐；由装配点从全局 Settings 构造注入
（与 agent/config.py 同一约定），测试可直接构造覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LegalRAGConfig:
    """子图检索与恢复参数（设计 §43/§49）。"""

    # 恢复循环上限（设计约束 19：一期不超过 3）
    max_retries: int = 2
    # 查询变体数量上限（设计 §23/§24/§25）
    max_subqueries: int = 5
    max_rewritten_queries: int = 2
    max_expanded_queries: int = 3
    # 单轮检索查询总数上限（设计 §26/§49：控制并发检索成本）
    max_retrieval_queries: int = 8
    # 混合检索参数（设计 §31）：dense/bm25 候选数由 Milvus 服务端
    # hybrid_search 统一处理，hybrid_top_k 为融合后返回量
    dense_top_k: int = 30
    bm25_top_k: int = 30
    hybrid_top_k: int = 20
    # 统一重排保留条数（设计 §34；进入回答上下文与「参考文档」展示）
    rerank_top_k: int = 10
    # RRF 融合参数（与 Milvus RRFRanker 口径一致，勿单独调整）
    rrf_k: int = 60
    # 证据充分性置信度阈值（evidence_grader_agent 参考）
    evidence_confidence_threshold: float = 0.80
