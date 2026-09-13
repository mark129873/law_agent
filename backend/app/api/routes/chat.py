"""Chat 流式路由。

DDD 说明：本路由是流式用例的"驱动适配器"——把 HTTP SSE 协议与
ChatService 的异步生成器对接；生成中任何异常都转为 error 事件
正常收尾，而不是让连接悬死，这是流式接口的可靠性契约。
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.dto import ChatStreamRequest
from app.api.errors import ConversationNotFoundApiError
from app.application.services.chat_service import ChatService
from app.application.services.conversation_service import ConversationNotFoundError

# 路由前缀统一挂在 /api/chat 下，具体端点只写子路径
router = APIRouter(prefix="/api/chat", tags=["chat"])

# SSE 响应头：
# - no-cache：禁止缓存流式响应，否则增量内容可能被代理整段缓冲
# - keep-alive：长连接持续推送
# - X-Accel-Buffering: no：显式告知 Nginx 等反向代理关闭缓冲，
#   保证每个 delta 事件实时到达前端（否则会"攒一波再吐"）
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse_event(payload: dict) -> str:
    """把一个事件字典编码为 SSE 帧。

    SSE 帧格式固定为 `data: {json}\\n\\n`（两个换行表示帧结束）；
    ensure_ascii=False 保证中文原样输出，前端无需二次解码。
    """
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def chat_stream(payload: ChatStreamRequest, request: Request) -> StreamingResponse:
    """提交问题并流式接收回答（SSE）。

    流式过程中任何异常都转为 error 事件发送后正常结束流，
    而不是让连接悬死——前端据此渲染错误提示。
    """
    # 依赖从容器解析（服务定位器经由 app.state），路由不自行构造服务
    chat_service: ChatService = request.app.state.container.resolve(ChatService)

    # 会话存在性在进入流之前校验：404 以普通 HTTP 状态码返回，
    # 让前端能用统一的错误处理逻辑消费；进入流之后再报错就只能
    # 走 error 事件，前端需要多处理一种失败形态
    try:
        await chat_service.ensure_conversation(payload.conversation_id)
    except ConversationNotFoundError as error:
        raise ConversationNotFoundApiError(str(error)) from error

    async def event_stream():
        # 领域事件 → SSE 帧的映射只存在这一份：
        # - status：节点执行状态（BE-041，前端浅色小字展示工作过程）
        # - plan：检索规划产出的全部查询（检索策略展示，重规划时再次出现）
        # - sources：RAG 检索有命中时出现（参考文档数据源，重规划后以最新一批为准）
        # - delta：逐段增量文本
        # - regenerating：校验打回重生成（前端据此清空已渲染增量）
        # - 正常结束追加 done 事件（带会话 id，前端可据此刷新会话列表）
        # - 任何异常（模型超时/服务内部错误）都转为 error 事件后正常
        #   结束流——已经推给前端的内容仍然有效，剩余部分以错误提示收尾
        try:
            async for event in chat_service.stream_answer(payload.conversation_id, payload.question):
                if event.type == "plan":
                    yield _sse_event({"type": "plan", "sub_queries": list(event.sub_queries)})
                elif event.type == "sources":
                    yield _sse_event({"type": "sources", "sources": list(event.sources)})
                elif event.type == "regenerating":
                    yield _sse_event({"type": "regenerating"})
                elif event.type == "status":
                    yield _sse_event({
                        "type": "status",
                        "node": event.node,
                        "label": event.label,
                        "phase": event.phase,
                        **({"duration_ms": event.duration_ms} if event.duration_ms is not None else {}),
                    })
                else:
                    yield _sse_event({"type": "delta", "content": event.content})
            yield _sse_event({"type": "done", "conversation_id": payload.conversation_id})
        except Exception as error:
            yield _sse_event({"type": "error", "message": f"生成回答失败：{error}"})

    # media_type 必须是 text/event-stream，这是 SSE 协议的标准 Content-Type
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)
