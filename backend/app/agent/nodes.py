"""Agent 图节点（命令模式）。

为什么用类而不是闭包工厂：节点是有身份的业务组件（可独立测试、
可替换、可组合），`__call__` 让实例直接充当 LangGraph 节点，
抽象基类 `AgentNode` 固定节点契约，新增节点时继承即可（多态）。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from langgraph.config import get_stream_writer

from app.agent.prompts import build_messages
from app.agent.state import AgentState
from app.application.services.rag_service import RagService
from app.domain.repositories.llm_provider import LLMProvider

logger = logging.getLogger("app.agent.nodes")


class AgentNode(ABC):
    """图节点基类：实现即命令（__call__ 使实例可直接注册为图节点）。"""

    @abstractmethod
    async def __call__(self, state: AgentState) -> dict:
        """处理工作流状态，返回本节点的状态增量。"""


class RetrieveNode(AgentNode):
    """检索节点：调用 RAG 服务把知识库上下文写入状态。"""

    def __init__(self, rag: RagService) -> None:
        self._rag = rag

    async def __call__(self, state: AgentState) -> dict:
        context = await self._rag.build_context(state["question"])
        return {"context": context}


class GenerateNode(AgentNode):
    """生成节点：组装 Prompt 并经 LLMProvider 流式生成回答。

    为什么在节点内通过 stream writer 推送 token：流式（astream + custom）
    与非流式（ainvoke）执行同一个节点实例，Prompt 组装与检索逻辑
    只有一份实现；非流式调用时 writer 事件无人消费，行为不变。
    """

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def __call__(self, state: AgentState) -> dict:
        messages = build_messages(
            question=state["question"],
            context=state.get("context", ""),
            history=state.get("history"),
        )
        logger.info(
            "Agent generate started",
            extra={"service": "agent", "model": self._llm.model_name, "message_count": len(messages)},
        )
        writer = get_stream_writer()
        collected: list[str] = []
        async for chunk in self._llm.stream(messages):
            collected.append(chunk)
            # astream(stream_mode="custom") 时事件会推送给调用方；ainvoke 时被忽略
            writer(chunk)
        answer = "".join(collected)
        logger.info(
            "Agent generate completed",
            extra={"service": "agent", "model": self._llm.model_name, "answer_length": len(answer)},
        )
        return {"answer": answer, "history": messages}
