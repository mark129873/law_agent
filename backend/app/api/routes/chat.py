"""Chat 流式路由（BE-020）。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.dto import ChatStreamRequest
from app.api.errors import ConversationNotFoundApiError
from app.application.services.chat_service import ChatService
from app.application.services.conversation_service import ConversationNotFoundError

router = APIRouter(prefix="/api/chat", tags=["chat"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # 禁用代理缓冲，保证增量事件实时到达前端
    "X-Accel-Buffering": "no",
}


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def chat_stream(payload: ChatStreamRequest, request: Request) -> StreamingResponse:
    """提交问题并流式接收回答（SSE）。

    流式过程中任何异常都转为 error 事件发送后正常结束流，
    而不是让连接悬死——前端据此渲染错误提示。
    """
    chat_service: ChatService = request.app.state.container.resolve(ChatService)

    # 会话存在性在进入流之前校验，让 404 以普通 HTTP 状态返回
    try:
        await chat_service.ensure_conversation(payload.conversation_id)
    except ConversationNotFoundError as error:
        raise ConversationNotFoundApiError(str(error)) from error

    async def event_stream():
        try:
            async for chunk in chat_service.stream_answer(payload.conversation_id, payload.question):
                yield _sse_event({"type": "delta", "content": chunk})
            yield _sse_event({"type": "done", "conversation_id": payload.conversation_id})
        except Exception as error:
            yield _sse_event({"type": "error", "message": f"生成回答失败：{error}"})

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)
