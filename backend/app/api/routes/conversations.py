"""会话与消息路由。

DDD 说明：控制器模式——HTTP 细节（状态码、JSON 形状）在这里终结，
业务规则全部在 ConversationService；会话不存在的领域异常在此翻译为
API 层的 404 错误，翻译边界清晰且只做一次。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.dto import ConversationResponse, CreateConversationRequest, MessageResponse
from app.api.errors import ConversationNotFoundApiError
from app.application.services.conversation_service import ConversationNotFoundError, ConversationService

# 路由前缀统一挂在 /api/conversations 下，具体端点只写子路径
router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _get_conversation_service(request: Request) -> ConversationService:
    """从容器解析会话服务：路由不自行构造依赖（服务定位器经由 app.state）。"""
    # 依赖从容器解析，路由内不构造任何基础设施组件
    return request.app.state.container.resolve(ConversationService)


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(payload: CreateConversationRequest, request: Request) -> ConversationResponse:
    """创建新会话。

    201 表示资源已创建（REST 惯例：POST 创建资源返回 201 而非 200），
    响应体直接携带新会话数据，前端无需二次查询。
    """
    conversation = await _get_conversation_service(request).create_conversation(payload.title)
    # 实体 → DTO：datetime 转 ISO 字符串，保证 JSON 可序列化且前端统一解析
    return ConversationResponse(
        id=conversation.id, title=conversation.title, created_at=conversation.created_at.isoformat()
    )


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(request: Request) -> list[ConversationResponse]:
    """会话列表：服务层保证按创建时间倒序（最新的在前，前端直接渲染）。"""
    conversations = await _get_conversation_service(request).list_conversations()
    return [
        ConversationResponse(id=c.id, title=c.title, created_at=c.created_at.isoformat()) for c in conversations
    ]


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(conversation_id: str, request: Request) -> list[MessageResponse]:
    """查询指定会话的全部消息（按时间正序，恢复对话上下文）。"""
    service = _get_conversation_service(request)
    try:
        messages = await service.get_messages(conversation_id)
    except ConversationNotFoundError as error:
        # 领域异常 → API 错误：翻译只在这里发生，Service 层不感知 HTTP
        raise ConversationNotFoundApiError(str(error)) from error
    # role 是枚举：取 .value 转字符串，避免枚举类型泄漏到 JSON
    return [
        MessageResponse(
            id=m.id,
            role=m.role.value,
            content=m.content,
            created_at=m.created_at.isoformat(),
            sources=m.sources,
        )
        for m in messages
    ]


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, request: Request) -> None:
    """删除会话（服务层级联清理其全部消息）。

    204 表示成功但无响应体——删除操作没有需要返回的资源，
    前端以状态码判断结果即可。
    """
    service = _get_conversation_service(request)
    try:
        await service.delete_conversation(conversation_id)
    except ConversationNotFoundError as error:
        raise ConversationNotFoundApiError(str(error)) from error
