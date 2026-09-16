"""聊天服务：问答流程编排（会话持久化 + LangGraph Agent）。

为什么所有问答都走 LangGraph 图的流式执行：对外唯一问答入口是 SSE
流式接口（stream_answer），检索、Prompt 组装、模型调用只有一份实现
（在图节点内），服务层只负责会话持久化与图执行，杜绝行为漂移。
Langfuse trace（BE-043）也挂在本服务：请求生命周期
（start_trace/end_trace）与流程事件（plan/think/sources/regenerating）
只有这里能看到全貌；节点 span 与 LLM generation 分别由图包装器与
LLMService 经同一 ContextVar 汇上报。
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Callable

from app.application.services.conversation_service import ConversationService
from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole
from app.domain.services.qa_workflow import QaStreamEvent, QaWorkflow
from app.domain.services.trace_sink import TraceSink, trace_sink_var

logger = logging.getLogger("app.chat.service")


class ChatService:
    """面向 API 层的问答编排。"""

    def __init__(
        self,
        conversation_service: ConversationService,
        qa_graph: QaWorkflow,
        trace_sink_factory: Callable[[], TraceSink | None] | None = None,
    ) -> None:
        self._conversations = conversation_service
        # 只依赖工作流端口：LangGraph 是可整体替换的实现细节
        self._graph = qa_graph
        # trace 汇工厂（BE-043）：None 表示未启用（不导入不构造观测实现）
        self._trace_sink_factory = trace_sink_factory

    async def ensure_conversation(self, conversation_id: str) -> None:
        """校验会话存在，供流式接口在进入流之前返回 404。"""
        await self._conversations.get_conversation(conversation_id)

    async def _snapshot_history(self, conversation_id: str) -> list[ChatMessage]:
        """会话历史快照（在保存新问题之前取，保证新问题不入历史）。"""
        history_entities = await self._conversations.get_messages(conversation_id)
        return [ChatMessage(role=m.role, content=m.content) for m in history_entities]

    async def stream_answer(
        self,
        conversation_id: str,
        question: str,
        *,
        use_web_search: bool = False,
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
            extra={
                "service": "chat",
                "conversation_id": conversation_id,
                "question_length": len(question),
                "use_web_search": use_web_search,
            },
        )
        history = await self._snapshot_history(conversation_id)
        await self._conversations.add_message(conversation_id, MessageRole.USER, question)

        collected: list[str] = []
        sources: list[dict[str, Any]] = []
        # Langfuse trace（BE-043）：每请求新建 sink 并注入上下文——图任务
        # 经 create_task 继承（节点 span/generation 上报的可见性基础）；
        # 工厂为 None（未启用）时 sink 恒 None，全部上报点跳过
        sink = self._trace_sink_factory() if self._trace_sink_factory is not None else None
        sink_token = trace_sink_var.set(sink) if sink is not None else None
        try:
            if sink is not None:
                sink.start_trace(session_id=conversation_id, question=question)
            # 检索与 Prompt 组装都在图节点内完成（图内部唯一实现）
            async for event in self._graph.astream(
                {
                    "question": question,
                    "history": history,
                    "conversation_id": conversation_id,
                    "web_search_requested": use_web_search,
                },
                stream_mode="custom",
            ):
                if event.type == "plan":
                    # 规划拆解：仅向下游转发（前端展示检索策略），不参与聚合
                    if sink is not None:
                        sink.record_event(
                            name="plan",
                            payload={"sub_queries": "；".join(event.sub_queries)},
                        )
                    yield event
                elif event.type == "sources":
                    # 参考来源：重规划补检索时会再次出现，保留最新一批
                    # （持久化的 sources 只记录最终生成所用的那批）
                    sources = [dict(item) for item in event.sources]
                    if sink is not None:
                        sink.record_event(name="sources", payload={"count": str(len(sources))})
                    yield event
                elif event.type == "web_sources":
                    # 网页来源与本地来源共享 sources 持久化契约，
                    # 但事件类型单独保留，前端可渲染不同的折叠区。
                    sources = [dict(item) for item in event.sources]
                    if sink is not None:
                        sink.record_event(name="web_sources", payload={"count": str(len(sources))})
                    yield event
                elif event.type == "web_search_notice":
                    # 配置缺失、空结果、远程失败和留档失败必须作为结构化 tag
                    # 传给 API，不能落入 delta 聚合或伪装成回答内容。
                    if sink is not None:
                        sink.record_event(
                            name="web_search_notice",
                            payload={"code": event.code, "message": event.message},
                        )
                    yield event
                elif event.type == "regenerating":
                    # verify 打回重生成：重置增量聚合，避免两版回答拼接
                    logger.info(
                        "Chat answer regenerating",
                        extra={"service": "chat", "conversation_id": conversation_id},
                    )
                    collected = []
                    if sink is not None:
                        sink.record_event(name="regenerating", payload={})
                    yield event
                elif event.type == "status":
                    # 节点执行状态（BE-041）：仅转发供前端展示工作过程，
                    # 绝不进入 delta 聚合——否则状态文本会被拼进回答
                    # （Langfuse 节点 span 由图任务内的包装器上报，不走此处）
                    yield event
                elif event.type == "think":
                    # 思考内容行（BE-042）：仅转发供前端思考块展示，
                    # 同样不进 delta 聚合（与 status 同一职责边界）
                    if sink is not None:
                        sink.record_event(
                            name="think", payload={"node": event.node, "text": event.text}
                        )
                    yield event
                else:
                    collected.append(event.content)
                    yield event
            full_answer = "".join(collected)
            if sink is not None:
                sink.end_trace(
                    output=full_answer,
                    metadata={
                        "source_count": str(len(sources)),
                        "answer_length": str(len(full_answer)),
                    },
                )
        except Exception as error:
            if sink is not None:
                sink.end_trace(error=str(error))
            logger.error(
                "Chat stream failed",
                extra={"service": "chat", "conversation_id": conversation_id, "error": str(error)},
            )
            raise
        finally:
            if sink_token is not None:
                trace_sink_var.reset(sink_token)
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
