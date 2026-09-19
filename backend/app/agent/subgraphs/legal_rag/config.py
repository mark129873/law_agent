"""Local Legal RAG 子图配置（BE-032，设计 §43）。

默认值与设计文档对齐；由装配点从全局 Settings 构造注入
（与 agent/config.py 同一约定），测试可直接构造覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LegalRAGConfig:
    """子图检索与恢复参数（设计 §43/§49）。"""

    # 恢复循环上限：首次无充分证据后最多再恢复检索一轮
    max_retries: int = 1
    # 查询变体数量上限（设计 §23/§24/§25）
    max_subqueries: int = 5
    max_rewritten_queries: int = 2
    max_expanded_queries: int = 3
    # 单轮检索查询总数上限（设计 §26/§49：控制并发检索成本）
    max_retrieval_queries: int = 8
    # 混合检索参数（设计 §31）：dense/bm25 每路独立取候选后交给 RRF 融合，
    # hybrid_top_k 为融合后最终返回量；装配点读取后注入 MilvusVectorStore
    dense_top_k: int = 30
    bm25_top_k: int = 30
    hybrid_top_k: int = 30
    # 统一重排保留条数（设计 §34；进入回答上下文与「参考文档」展示）
    rerank_top_k: int = 10
    # 重排前按 RRF 分预截断的候选上限（粗排→精排：跨查询候选可达 8×30，
    # 只把最有希望的候选交给 CrossEncoder；适度扩大候选池，避免恢复查询
    # 找到的具体法条在全局粗排阶段被过早丢弃。）
    rerank_max_candidates: int = 32
    # RRF 融合平滑常数（论文推荐值 60，排名越靠前贡献越大）；装配点注入 Milvus RRFRanker
    rrf_k: int = 60
    # 证据充分性置信度阈值（evidence_grader_agent 参考）
    evidence_confidence_threshold: float = 0.80
