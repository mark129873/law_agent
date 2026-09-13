"""Agent 工作流状态定义。

为什么用 TypedDict 而不是 dataclass：LangGraph 的状态通道
以字典协议读写，TypedDict 是其官方推荐形式，
同时保留静态类型检查能力。
"""

from __future__ import annotations

from typing import TypedDict

from app.domain.entities.llm import ChatMessage


class AgentState(TypedDict, total=False):
    """Agent 工作流状态：节点间只通过此结构传递数据。

    BE-030 统一规划闭环新增字段：子查询列表、verify 判定与反馈、
    各节点执行次数（预算计数，防止反馈环死循环）。
    """

    question: str
    history: list[ChatMessage]
    context: str  # RAG 检索上下文；知识库空命中时为空串（走信息不足策略）
    answer: str
    # ---- BE-030 Plan-and-Execute 闭环 ----
    sub_queries: list[str]  # 规划器产出的子查询（简单问题为 [原问题]）
    verify_verdict: str  # verify 判定：pass / grounding / contract
    verify_feedback: str  # 打回时携带的修正建议（无依据结论清单或契约问题）
    plan_runs: int  # plan 节点已执行次数（预算上限 2）
    generate_runs: int  # generate 节点已执行次数（预算上限 2）
