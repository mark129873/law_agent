"""API 层请求/响应 DTO。

为什么独立于领域实体：HTTP 契约需要稳定且面向前端
（如时间戳格式化、id 字符串化），实体变更不应直接击穿接口。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: str = ""


class ChatStreamRequest(BaseModel):
    conversation_id: str
    question: str = Field(min_length=1)


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: str


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class DocumentResponse(BaseModel):
    id: str
    filename: str
    file_size: int
    status: str
    created_at: str


class ErrorResponse(BaseModel):
    """统一错误结构，所有非 2xx 响应均为该形状。"""

    code: int
    message: str
