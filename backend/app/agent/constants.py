"""Agent 模块统一常量（BE-032）。

为什么集中定义：节点名、状态字面量、中文展示标签是主图、子图、
SSE 协议与前端展示之间的一致性契约，散落各处必然漂移；
本模块只放字面量与映射，不放任何逻辑（纯常量模块）。
"""

from __future__ import annotations

# ---- Query Router：意图与请求类型（设计 §8.1）----
INTENT_LEGAL_QUESTION = "legal_question"      # 法律事实型问题（默认走知识库检索）
INTENT_GENERAL_QUESTION = "general_question"  # 一般性对话/概念解释（走直接回答）
INTENT_PLUGIN_REQUEST = "plugin_request"      # 插件能力请求
INTENT_WEB_REQUEST = "web_request"            # 网络搜索请求
INTENT_OTHER = "other"

REQUEST_TYPE_LOCAL_RAG = "local_rag"
REQUEST_TYPE_PLUGIN = "plugin"
REQUEST_TYPE_WEB = "web"
REQUEST_TYPE_DIRECT = "direct"

# ---- Orchestrator：顶层动作（设计 §8.2）----
ACTION_LOCAL_RAG = "local_rag"
ACTION_PLUGIN = "plugin"
ACTION_WEB_SEARCH = "web_search"
ACTION_DIRECT_ANSWER = "direct_answer"
ACTION_FINISH = "finish"

# ---- Capability 统一状态（设计 §10）----
CAPABILITY_SUCCESS = "SUCCESS"
CAPABILITY_LOCAL_EVIDENCE_INSUFFICIENT = "LOCAL_EVIDENCE_INSUFFICIENT"
CAPABILITY_NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
CAPABILITY_DISABLED = "DISABLED"
CAPABILITY_RETRIEVAL_ERROR = "RETRIEVAL_ERROR"

# ---- RAG 子图状态（设计 §38/§47）----
RAG_STATUS_SUCCESS = "SUCCESS"
RAG_STATUS_LOCAL_EVIDENCE_INSUFFICIENT = "LOCAL_EVIDENCE_INSUFFICIENT"
RAG_STATUS_RETRIEVAL_ERROR = "RETRIEVAL_ERROR"

# ---- 检索查询类型（设计 §26）----
QUERY_TYPE_ORIGINAL = "original"
QUERY_TYPE_REWRITE = "rewrite"
QUERY_TYPE_SUBQUERY = "subquery"
QUERY_TYPE_EXPANSION = "expansion"

# ---- 节点中文展示标签（D5：status SSE 事件的前端文案）----
# 为什么用映射表而不是节点自报：label 是展示层文案，统一在一处维护
# 可保证 SSE 事件、日志与前端渲染三方一致；新增节点必须在此登记。
NODE_LABELS: dict[str, str] = {
    # 主图节点
    "query_router_agent": "理解问题",
    "orchestrator_agent": "规划下一步",
    "action_router_node": "确定执行路径",
    "legal_rag_subgraph": "检索知识库",
    "web_search_entry_node": "检查网络搜索",
    "web_search_stub_node": "网络搜索（未开通）",
    "plugin_entry_node": "检查插件能力",
    "plugin_stub_node": "插件能力（未开通）",
    "direct_answer_agent": "生成回答",
    "observation_node": "汇总结果",
    "answer_generator_agent": "生成回答",
    "grounding_checker_agent": "校验回答依据",
    "final_answer_node": "整理引用来源",
    # Local Legal RAG 子图节点
    "retrieval_planner_agent": "规划检索策略",
    "strategy_router_node": "执行检索计划",
    "query_rewrite_agent": "改写查询",
    "subquery_generator_agent": "拆解子问题",
    "query_expansion_agent": "扩展法律术语",
    "hybrid_retriever_node": "混合检索知识库",
    "evidence_ranking_node": "重排证据",
    "evidence_grader_agent": "评估证据充分性",
    "recovery_planner_agent": "制定恢复计划",
    "rag_result_node": "整理检索结果",
}


def node_label(node_name: str) -> str:
    """取节点中文标签；未登记节点回退为节点名本身（不阻塞流程）。"""
    return NODE_LABELS.get(node_name, node_name)
