"""会话与消息路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.dto import ConversationResponse, CreateConversationRequest, MessageResponse
from app.api.errors import ConversationNotFoundApiError
from app.application.services.conversation_service import ConversationNotFoundError, ConversationService

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _get_conversation_service(request: Request) -> ConversationService:
    # 依赖从容器解析，路由内不构造任何基础设施组件
    return request.app.state.container.resolve(ConversationService)


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(payload: CreateConversationRequest, request: Request) -> ConversationResponse:
    conversation = await _get_conversation_service(request).create_conversation(payload.title)
    return ConversationResponse(
        id=conversation.id, title=conversation.title, created_at=conversation.created_at.isoformat()
    )


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(request: Request) -> list[ConversationResponse]:
    conversations = await _get_conversation_service(request).list_conversations()
    return [
        ConversationResponse(id=c.id, title=c.title, created_at=c.created_at.isoformat()) for c in conversations
    ]


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(conversation_id: str, request: Request) -> list[MessageResponse]:
    service = _get_conversation_service(request)
    try:
        messages = await service.get_messages(conversation_id)
    except ConversationNotFoundError as error:
        raise ConversationNotFoundApiError(str(error)) from error
    return [
        MessageResponse(id=m.id, role=m.role.value, content=m.content, created_at=m.created_at.isoformat())
        for m in messages
    ]


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, request: Request) -> None:
    service = _get_conversation_service(request)
    try:
        await service.delete_conversation(conversation_id)
    except ConversationNotFoundError as error:
        raise ConversationNotFoundApiError(str(error)) from error
