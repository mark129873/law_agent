"""API 层请求/响应 DTO。

为什么独立于领域实体：HTTP 契约需要稳定且面向前端
（如时间戳格式化、id 字符串化），实体变更不应直接击穿接口。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    """创建会话请求体：title 可选（空标题由服务层回退默认值）。"""
    title: str = ""


class ChatStreamRequest(BaseModel):
    """流式问答请求体；question 最少 1 字符由 pydantic 校验兜底。"""
    conversation_id: str
    question: str = Field(min_length=1)


class ConversationResponse(BaseModel):
    """会话响应：created_at 已转为 ISO 字符串，前端无需处理时间对象。"""
    id: str
    title: str
    created_at: str


class MessageResponse(BaseModel):
    """消息响应：role 以字符串输出，避免枚举类型泄漏到 JSON。"""
    id: str
    role: str
    content: str
    created_at: str


class DocumentResponse(BaseModel):
    """知识库文档响应：status 为处理状态机的字符串形式（pending/processing/ready/failed）。"""
    id: str
    filename: str
    file_size: int
    status: str
    created_at: str


class ErrorResponse(BaseModel):
    """统一错误结构，所有非 2xx 响应均为该形状。"""

    code: int
    message: str
