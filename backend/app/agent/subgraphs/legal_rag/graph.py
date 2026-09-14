"""Local Legal RAG 子图组装（BE-035，设计 §4/§45）。

为什么独立构建（约束 4/5）：子图可独立 ainvoke 测试与复用，
作为编译图节点接入主图时按同名通道传递状态——
original_query/normalized_query 流入，rag_status/ranked_evidence/
missing_evidence/suggested_external_queries 回写主图
（LegalRAGState 中其余键为子图内部状态，不外泄）。
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.node_status import add_node_traced
from app.agent.services.llm_service import LLMService
from app.agent.services.milvus_service import MilvusService
from app.agent.services.reranker_service import RerankerService
from app.agent.subgraphs.legal_rag.config import LegalRAGConfig
from app.agent.subgraphs.legal_rag.nodes import (
    EvidenceGraderAgent,
    EvidenceRankingNode,
    HybridRetrieverNode,
    QueryExpansionAgent,
    QueryRewriteAgent,
    RagResultNode,
    RecoveryPlannerAgent,
    RetrievalPlannerAgent,
    StrategyRouterNode,
    SubqueryGeneratorAgent,
    route_strategies,
)
from app.agent.subgraphs.legal_rag.state import LegalRAGState

# 策略 fan-out 的全部可能目标（条件边声明，供图渲染与校验）
_STRATEGY_TARGETS = [
    "query_rewrite_agent",
    "subquery_generator_agent",
    "query_expansion_agent",
    "hybrid_retriever_node",
]


def build_legal_rag_graph(
    llm: LLMService,
    milvus: MilvusService,
    reranker: RerankerService,
    config: LegalRAGConfig | None = None,
) -> CompiledStateGraph:
    """装配 Local Legal RAG 子图（设计 §4 拓扑）。

    依赖经参数注入（三个服务 + 配置），装配与执行分离——
    测试以 Fake 服务构建同一拓扑（设计 §51 Mock 要求）。
    """
    config = config or LegalRAGConfig()
    builder = StateGraph(LegalRAGState)

    # 全部节点经 with_node_status 包装（BE-041）：起止 status 事件 + 日志
    add_node_traced(builder, "retrieval_planner_agent", RetrievalPlannerAgent(llm, config))
    add_node_traced(builder, "strategy_router_node", StrategyRouterNode())
    add_node_traced(builder, "query_rewrite_agent", QueryRewriteAgent(llm, config))
    add_node_traced(builder, "subquery_generator_agent", SubqueryGeneratorAgent(llm, config))
    add_node_traced(builder, "query_expansion_agent", QueryExpansionAgent(llm, config))
    add_node_traced(builder, "hybrid_retriever_node", HybridRetrieverNode(milvus, config))
    add_node_traced(builder, "evidence_ranking_node", EvidenceRankingNode(reranker, config))
    add_node_traced(builder, "evidence_grader_agent", EvidenceGraderAgent(llm, config))
    add_node_traced(builder, "recovery_planner_agent", RecoveryPlannerAgent(llm, config))
    add_node_traced(builder, "rag_result_node", RagResultNode())

    builder.add_edge(START, "retrieval_planner_agent")
    builder.add_edge("retrieval_planner_agent", "strategy_router_node")
    # 多选策略 fan-out（约束 15）：条件边返回列表即并行执行，
    # 全部分支经静态边汇入 hybrid_retriever_node（约束 16）
    builder.add_conditional_edges(
        "strategy_router_node", route_strategies, _STRATEGY_TARGETS
    )
    for variant in ("query_rewrite_agent", "subquery_generator_agent", "query_expansion_agent"):
        builder.add_edge(variant, "hybrid_retriever_node")
    builder.add_edge("hybrid_retriever_node", "evidence_ranking_node")
    builder.add_edge("evidence_ranking_node", "evidence_grader_agent")
    # 证据评估后路由：充分 → 结果；预算内可恢复 → 恢复规划（回 strategy_router，
    # 形成设计 §37 的本地恢复循环）；否则 → 结果
    builder.add_conditional_edges(
        "evidence_grader_agent",
        route_after_evidence_grade(config),
        {"recover": "recovery_planner_agent", "result": "rag_result_node"},
    )
    builder.add_edge("recovery_planner_agent", "strategy_router_node")
    builder.add_edge("rag_result_node", END)
    return builder.compile()


def route_after_evidence_grade(config: LegalRAGConfig):
    """证据评估后的路由函数工厂（设计 §46.2）。

    为什么用工厂闭包而不是读全局：max_retries 是配置值，路由条件
    随配置变化；闭包把配置固定进路由函数，图装配期一次确定。

    为什么预算检查在条件边而不是恢复规划节点：恢复规划是"怎么补救"，
    预算是"还要不要补救"——路由问题归条件边，节点保持纯粹；
    两处分离也不会出现"事件已推、实际未打回"的漂移（打回不推事件）。
    """
    def _route(state: LegalRAGState) -> str:
        if state.get("evidence_sufficient"):
            return "result"
        if state.get("local_recovery_possible") and state.get("retry_count", 0) < config.max_retries:
            return "recover"
        return "result"

    return _route
