"""LangGraph Agent 工作流。

为什么用 LangGraph 而不是直接函数调用：问答流程即将扩展出
检索、上下文改写、多轮工具调用等节点，图结构让节点职责与
执行顺序显式化，且天然支持异步节点与状态流转。
"""

from __future__ import annotations

import logging

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from app.agent.prompts import build_messages
from app.agent.state import AgentState
from app.application.services.rag_service import RagService
from app.domain.entities.message import MessageRole
from app.domain.repositories.llm_provider import LLMProvider

logger = logging.getLogger("app.agent.graph")


def _make_generate_node(llm: LLMProvider):
    """生成节点：组装 Prompt 并调用 LLM。"""

    async def generate(state: AgentState) -> dict:
        messages = build_messages(
            question=state["question"],
            context=state.get("context", ""),
            history=state.get("history"),
        )
        logger.info(
            "Agent generate started",
            extra={"service": "agent", "model": llm.model_name, "message_count": len(messages)},
        )
        answer = await llm.chat(messages)
        logger.info("Agent generate completed", extra={"service": "agent", "model": llm.model_name})
        return {"answer": answer, "history": messages}

    return generate


def _make_retrieve_node(rag: RagService):
    """检索节点：调用 RAG 服务获取知识库上下文（BE-016）。"""

    async def retrieve(state: AgentState) -> dict:
        context = await rag.build_context(state["question"])
        return {"context": context}

    return retrieve


def build_qa_graph(llm: LLMProvider, rag: RagService | None = None) -> CompiledStateGraph:
    """构建问答工作流。

    为什么 rag 允许为 None：BE-015 的基础工作流不依赖知识库；
    传入 rag 即升级为 RAG 工作流（BE-016），图结构对调用方透明。
    """
    builder = StateGraph(AgentState)
    if rag is not None:
        builder.add_node("retrieve", _make_retrieve_node(rag))
        builder.add_edge(START, "retrieve")
        builder.add_edge("retrieve", "generate")
    else:
        builder.add_edge(START, "generate")
    builder.add_node("generate", _make_generate_node(llm))
    builder.add_edge("generate", END)
    return builder.compile()


async def run_qa(
    graph: CompiledStateGraph,
    question: str,
    history: list | None = None,
) -> str:
    """执行一次问答，返回模型回答（对上层隐藏图状态细节）。"""
    result = await graph.ainvoke({"question": question, "history": history or []})
    return result["answer"]
