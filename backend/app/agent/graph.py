"""LangGraph 问答工作流：建造者 + 端口适配器。

为什么这样拆分：
- `QaGraphBuilder`（建造者模式）负责把节点装配成图，装配规则集中一处；
- `LangGraphQaWorkflow`（适配器模式）显式实现 QaWorkflow 领域端口，
  把 langgraph 引擎封在适配器之内——引擎可替换而端口不变。
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from app.agent.nodes import GenerateNode, RetrieveNode
from app.agent.prompts import build_messages
from app.agent.state import AgentState
from app.application.services.rag_service import RagService
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.services.qa_workflow import QaWorkflow

logger = logging.getLogger("app.agent.graph")


class QaGraphBuilder:
    """问答工作流建造者：按是否有 RAG 服务装配不同拓扑。"""

    def __init__(self, llm: LLMProvider, rag: RagService | None = None) -> None:
        self._llm = llm
        self._rag = rag

    def build(self) -> CompiledStateGraph:
        builder = StateGraph(AgentState)
        if self._rag is not None:
            builder.add_node("retrieve", RetrieveNode(self._rag))
            builder.add_edge(START, "retrieve")
            builder.add_edge("retrieve", "generate")
        else:
            builder.add_edge(START, "generate")
        builder.add_node("generate", GenerateNode(self._llm))
        builder.add_edge("generate", END)
        return builder.compile()


class LangGraphQaWorkflow(QaWorkflow):
    """QaWorkflow 端口的 LangGraph 适配器（显式实现领域端口）。

    为什么显式继承协议：让"本类是端口的实现"成为类型系统事实，
    也让 issubclass/isinstance 校验在装配点可用。
    """

    def __init__(self, graph: CompiledStateGraph) -> None:
        self._graph = graph

    async def ainvoke(self, input: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return await self._graph.ainvoke(input, **kwargs)

    def astream(self, input: dict[str, Any], **kwargs: Any) -> AsyncIterator[Any]:
        return self._graph.astream(input, **kwargs)


def build_qa_graph(llm: LLMProvider, rag: RagService | None = None) -> CompiledStateGraph:
    """兼容入口：等价于 QaGraphBuilder(llm, rag).build()（测试与脚本使用）。"""
    return QaGraphBuilder(llm, rag).build()


async def run_qa(
    graph: CompiledStateGraph | QaWorkflow,
    question: str,
    history: list | None = None,
) -> str:
    """执行一次问答，返回模型回答（对上层隐藏图状态细节）。"""
    result = await graph.ainvoke({"question": question, "history": history or []})
    return result["answer"]
