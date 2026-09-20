"""主图 Agent 状态（BE-032，设计 §6 经端口契约适配）。

为什么保留 question/history/answer 三个"端口兼容键"：QaWorkflow
领域端口与 ChatService 以 {"question","history"} 输入、answer 输出
为契约，主图状态必须兼容，重写才不外泄到应用层；
其余字段按设计文档 §6 命名。

为什么 trace 用 Annotated[list, operator.add]：通道统一走"追加"
语义（节点只返回自己的增量条目）；主图当前没有同超步并行写，
但追加归约器让"每节点写 trace"这一约定在任何拓扑下都安全
（子图存在策略 fan-out 并行，见 legal_rag/state.py 的同类说明）。

为什么主图声明 rag_status/ranked_evidence 等键：legal_rag 子图作为
编译图节点接入时，LangGraph 按同名通道回传状态——只有主图声明了
的子图输出键才会回写（rag_trace 等子图内部键不回传，避免污染）。
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from app.domain.entities.llm import ChatMessage


class AgentState(TypedDict, total=False):
    # ---- 输入（QaWorkflow 端口契约）----
    question: str               # 用户原始问题（original_query 的输入载体）
    history: list[ChatMessage]  # 会话历史快照
    conversation_id: str        # 当前会话 id，用于搜索留档与请求追踪

    # ---- Query Router（设计 §6）----
    original_query: str
    normalized_query: str
    web_search_requested: bool  # 仅由前端按钮传入，是真正联网调用的唯一信号
    intent: str
    request_type: str
    extracted_conditions: dict[str, Any]

    # ---- Orchestrator ----
    current_action: str
    action_reason: str
    global_step_count: int
    max_global_steps: int

    # ---- Capability Result（observation_node 归一后）----
    last_capability: str
    capability_status: str
    capability_result: dict[str, Any]

    # ---- Evidence / Citation ----
    evidence: list[dict[str, Any]]
    citations: list[dict[str, Any]]

    # ---- Legal RAG 子图回写键（同名通道回传）----
    rag_status: str
    ranked_evidence: list[dict[str, Any]]
    missing_evidence: list[str]
    suggested_external_queries: list[str]

    # ---- Answer ----
    answer_draft: str
    final_answer: str
    answer: str  # 端口兼容输出键（= final_answer，ChatService/run_qa 消费）

    # ---- Grounding ----
    grounding_passed: bool
    grounding_issues: list[str]

    # ---- Trace（追加语义）----
    trace: Annotated[list[dict[str, Any]], operator.add]
