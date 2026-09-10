"""HTTP 请求链路标识中间件。

为什么需要：docs/RELIABILITY.md 要求日志能把「HTTP 请求 → 检索 → LLM 调用 → 落库」
串成一条线；给每个请求分配一个 request_id 并注入日志上下文即可实现，
业务代码完全不需要感知 request_id 的存在。

为什么用纯 ASGI 中间件而不是 FastAPI 的 @app.middleware("http")：
后者基于 BaseHTTPMiddleware，会缓冲/包装响应体，对本项目的 SSE
（StreamingResponse 长连接流式输出）存在破坏风险；纯 ASGI 实现只透传
receive/send，对流式响应零干扰。

DDD/OOP：本模块属于 API 层横切设施，只依赖 common 层的日志上下文工具，
不依赖任何基础设施实现（符合 API 层只能依赖领域端口/common 的边界规则）。
"""

from __future__ import annotations

import uuid
from typing import Any, Awaitable, Callable

from app.common.logging import reset_request_id, set_request_id

# 请求头键（ASGI 中以小写 bytes 形式出现）
_HEADER = b"x-request-id"


class RequestIdMiddleware:
    """为每个 HTTP 请求分配 request_id，写入日志上下文与响应头。"""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
        # 非 HTTP 作用域（如 lifespan/websocket）不处理，直接透传
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 优先沿用上游传入的标识（便于跨服务/网关追踪），没有则生成短随机串
        incoming = ""
        for key, value in scope.get("headers", []):
            if key.lower() == _HEADER:
                incoming = value.decode("latin-1")
                break
        request_id = incoming or uuid.uuid4().hex[:12]

        token = set_request_id(request_id)

        async def send_with_header(message: dict[str, Any]) -> None:
            # 在响应起始消息回写 request_id，排障时可据此关联后端日志
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((_HEADER, request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            # 请求结束还原上下文，避免污染后续任务（含同 worker 的下一个请求）
            reset_request_id(token)
