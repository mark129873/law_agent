"""聊天服务：问答流程编排（会话持久化 + RAG 检索 + LLM 调用）。

为什么流式不走 LangGraph 图：非流式回答复用已验证的 Agent 图；
流式路径需要逐 token 边生成边推送，直接使用 LLMProvider.stream
配合相同的 build_messages 组装，保证两条路径的 Prompt 完全一致。
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from app.agent.graph import CompiledStateGraph, run_qa
from app.agent.prompts import build_messages
from app.application.services.conversation_service import ConversationService
from app.application.services.rag_service import RagService
from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import Message, MessageRole
from app.domain.repositories.llm_provider import LLMProvider

logger = logging.getLogger("app.chat.service")


class ChatService:
    """面向 API 层的问答编排。"""

    def __init__(
        self,
        conversation_service: ConversationService,
        rag_service: RagService,
        llm_provider: LLMProvider,
        qa_graph: CompiledStateGraph,
    ) -> None:
        self._conversations = conversation_service
        self._rag = rag_service
        self._llm = llm_provider
        self._graph = qa_graph

    async def _prepare(self, conversation_id: str, question: str) -> tuple[list[ChatMessage], list[ChatMessage]]:
        """公共前置：历史消息 + 检索上下文 + Prompt 组装。

        返回 (prompt_messages, history_messages)，history 用于持久化判断。
        """
        history_entities = await self._conversations.get_messages(conversation_id)
        history = [ChatMessage(role=m.role, content=m.content) for m in history_entities]
        context = await self._rag.build_context(question)
        return build_messages(question, context, history), history

    async def ensure_conversation(self, conversation_id: str) -> None:
        """校验会话存在，供流式接口在进入流之前返回 404。"""
        await self._conversations.get_conversation(conversation_id)

    async def send_message(self, conversation_id: str, question: str) -> tuple[Message, Message]:
        """非流式问答：走 Agent 图，返回持久化后的（用户消息, 回答消息）。"""
        prompt_messages, _ = await self._prepare(conversation_id, question)
        user_message = await self._conversations.add_message(conversation_id, MessageRole.USER, question)
        answer = await run_qa(self._graph, question, history=prompt_messages[1:-1])
        assistant_message = await self._conversations.add_message(conversation_id, MessageRole.ASSISTANT, answer)
        return user_message, assistant_message

    async def stream_answer(self, conversation_id: str, question: str) -> AsyncIterator[str]:
        """流式问答：逐 token 推送增量；流结束前持久化完整问答。

        为什么在生成器内持久化：只有在正常完成时才落库，
        异常中断的回答不完整，不应以完整消息的形式入库。
        """
        prompt_messages, _ = await self._prepare(conversation_id, question)
        await self._conversations.add_message(conversation_id, MessageRole.USER, question)

        collected: list[str] = []
        try:
            async for chunk in self._llm.stream(prompt_messages):
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
                "model": self._llm.model_name,
            },
        )
