"""Agent 工作流状态定义。

为什么用 TypedDict 而不是 dataclass：LangGraph 的状态通道
以字典协议读写，TypedDict 是其官方推荐形式，
同时保留静态类型检查能力。
"""

from __future__ import annotations

from typing import TypedDict

from app.domain.entities.llm import ChatMessage


class AgentState(TypedDict, total=False):
    """Agent 工作流状态：节点间只通过此结构传递数据。"""

    question: str
    history: list[ChatMessage]
    context: str  # RAG 检索上下文；基础工作流中为空串
    answer: str
