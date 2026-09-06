"""聊天服务：问答流程编排（会话持久化 + LangGraph Agent）。

为什么所有问答都走 LangGraph 图：流式与非流式共享同一个工作流，
检索、Prompt 组装、模型调用只有一份实现（在图节点内），
服务层只负责会话持久化与图执行，杜绝两条路径行为漂移。
"""

from __future__ import annotations

import logging
import time
from typing import AsyncIterator

from app.application.services.conversation_service import ConversationService
from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole
from app.domain.services.qa_workflow import QaStreamEvent, QaWorkflow

logger = logging.getLogger("app.chat.service")


class ChatService:
    """面向 API 层的问答编排。"""

    def __init__(
        self,
        conversation_service: ConversationService,
        qa_graph: QaWorkflow,
    ) -> None:
        self._conversations = conversation_service
        # 只依赖工作流端口：LangGraph 是可整体替换的实现细节
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
        started_at = time.perf_counter()
        # 埋点规则（RELIABILITY.md）：问答任务开始
        logger.info(
            "Chat task started",
            extra={"service": "chat", "conversation_id": conversation_id, "question_length": len(question)},
        )
        history = await self._snapshot_history(conversation_id)
        await self._conversations.add_message(conversation_id, MessageRole.USER, question)
        # 只经端口调用工作流：answer 字段由图状态返回（见 AgentState）
        result = await self._graph.ainvoke({"question": question, "history": history})
        # 埋点规则（RELIABILITY.md）：生成回答记录耗时
        # （回答置信度由检索侧记录：RagService 的 top_score 即检索相关度置信度）
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            "Chat answer generated",
            extra={
                "service": "chat",
                "conversation_id": conversation_id,
                "answer_length": len(result["answer"]),
                "duration_ms": duration_ms,
            },
        )
        return result["answer"]

    async def stream_answer(
        self, conversation_id: str, question: str
    ) -> AsyncIterator[QaStreamEvent]:
        """流式问答：走 Agent 图（astream + custom 模式），逐事件产出领域事件。

        为什么在生成器内持久化：只有在正常完成时才落库，
        异常中断的回答不完整，不应以完整消息的形式入库。
        参考来源（sources 事件）随回答一起持久化——历史会话恢复后
        前端才能继续展示"参考文档"（FE-011），而非只在本次会话内可见。
        """
        started_at = time.perf_counter()
        # 埋点规则（RELIABILITY.md）：问答任务开始
        logger.info(
            "Chat task started",
            extra={"service": "chat", "conversation_id": conversation_id, "question_length": len(question)},
        )
        history = await self._snapshot_history(conversation_id)
        await self._conversations.add_message(conversation_id, MessageRole.USER, question)

        collected: list[str] = []
        sources: list[dict[str, str]] = []
        try:
            # 检索与 Prompt 组装都在图节点内完成（与 send_message 同一路径）
            async for event in self._graph.astream(
                {"question": question, "history": history}, stream_mode="custom"
            ):
                if event.type == "sources":
                    # 参考来源：记录供持久化，并原样向下游转发（先于全部 delta）
                    sources = [dict(item) for item in event.sources]
                    yield event
                else:
                    collected.append(event.content)
                    yield event
        except Exception as error:
            logger.error(
                "Chat stream failed",
                extra={"service": "chat", "conversation_id": conversation_id, "error": str(error)},
            )
            raise
        full_answer = "".join(collected)
        await self._conversations.add_message(
            conversation_id, MessageRole.ASSISTANT, full_answer, sources=sources or None
        )
        # 埋点规则（RELIABILITY.md）：生成回答记录耗时（置信度见 RagService top_score）
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            "Chat stream completed",
            extra={
                "service": "chat",
                "conversation_id": conversation_id,
                "answer_length": len(full_answer),
                "source_count": len(sources),
                "duration_ms": duration_ms,
            },
        )
