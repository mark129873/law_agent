"""聊天服务：问答流程编排（会话持久化 + LangGraph Agent）。

为什么所有问答都走 LangGraph 图：流式与非流式共享同一个工作流，
检索、Prompt 组装、模型调用只有一份实现（在图节点内），
服务层只负责会话持久化与图执行，杜绝两条路径行为漂移。
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from langgraph.graph.state import CompiledStateGraph

from app.agent.graph import run_qa
from app.application.services.conversation_service import ConversationService
from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

logger = logging.getLogger("app.chat.service")


class ChatService:
    """面向 API 层的问答编排。"""

    def __init__(
        self,
        conversation_service: ConversationService,
        qa_graph: CompiledStateGraph,
    ) -> None:
        self._conversations = conversation_service
        self._graph = qa_graph

    async def ensure_conversation(self, conversation_id: str) -> None:
        """校验会话存在，供流式接口在进入流之前返回 404。"""
        await self._conversations.get_conversation(conversation_id)

    async def _snapshot_history(self, conversation_id: str) -> list[ChatMessage]:
        """会话历史快照（在保存新问题之前取，保证新问题不入历史）。"""
        history_entities = await self._conversations.get_messages(conversation_id)
        return [ChatMessage(role=m.role, content=m.content) for m in history_entities]

    async def send_message(self, conversation_id: str, question: str) -> str:
        """非流式问答：走 Agent 图（ainvoke），返回完整回答。

        为什么与流式共用图：检索与 Prompt 组装只存在图节点内一份实现，
        两条路径永远不会出现 Prompt 或上下文不一致。
        """
        history = await self._snapshot_history(conversation_id)
        await self._conversations.add_message(conversation_id, MessageRole.USER, question)
        return await run_qa(self._graph, question, history=history)

    async def stream_answer(self, conversation_id: str, question: str) -> AsyncIterator[str]:
        """流式问答：走 Agent 图（astream + custom 模式），逐 token 推送增量。

        为什么在生成器内持久化：只有在正常完成时才落库，
        异常中断的回答不完整，不应以完整消息的形式入库。
        """
        history = await self._snapshot_history(conversation_id)
        await self._conversations.add_message(conversation_id, MessageRole.USER, question)

        collected: list[str] = []
        try:
            # 检索与 Prompt 组装都在图节点内完成（与 send_message 同一路径）
            async for chunk in self._graph.astream(
                {"question": question, "history": history}, stream_mode="custom"
            ):
                collected.append(chunk)
                yield chunk
        except Exception as error:
            logger.error(
                "Chat stream failed",
                extra={"service": "chat", "conversation_id": conversation_id, "error": str(error)},
            )
            raise
        full_answer = "".join(collected)
        await self._conversations.add_message(conversation_id, MessageRole.ASSISTANT, full_answer)
        logger.info(
            "Chat stream completed",
            extra={
                "service": "chat",
                "conversation_id": conversation_id,
                "answer_length": len(full_answer),
            },
        )
