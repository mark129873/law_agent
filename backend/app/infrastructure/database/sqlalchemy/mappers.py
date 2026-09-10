"""领域实体 ↔ ORM 模型的显式映射（Data Mapper 模式，BE-025）。

为什么必须有这一层：
- 领域实体是纯 dataclass，零技术依赖（DDD 边界守护测试强制）；
- ORM 模型带 sqlalchemy 依赖，只能住在 infrastructure；
- 两者无法合并成一个类，于是把"怎么互相转换"集中到本文件，
  仓储方法里只做"取模型 → 转实体"与"转模型 → 存"，不再各写一份字段清单。
  字段增删只会在本文件暴露，避免散落式漂移。

约定：
- 出口（to_domain_*）：ORM 模型 → 领域实体，仓储返回给上层的一律是实体；
- 入口（to_model_*）：领域实体 → ORM 模型，新对象用于 session.add；
- sources 的 JSON 编解码固定在这里（ensure_ascii=False，中文原样可读），
  与既有数据库文件的存储格式保持一致。
"""

from __future__ import annotations

import json

from app.domain.entities.conversation import Conversation
from app.domain.entities.document import Document, DocumentStatus
from app.domain.entities.message import Message, MessageRole
from app.infrastructure.database.sqlalchemy.models import (
    ConversationModel,
    DocumentModel,
    MessageModel,
)


# ---------- Conversation ----------

def conversation_to_domain(model: ConversationModel) -> Conversation:
    """ORM 模型 -> Conversation 实体（仓储出口统一走这里）。"""
    return Conversation(id=model.id, title=model.title, created_at=model.created_at)


def conversation_to_model(entity: Conversation) -> ConversationModel:
    """Conversation 实体 -> ORM 模型（新建时使用；id 由仓储保证已赋值）。"""
    return ConversationModel(id=entity.id, title=entity.title, created_at=entity.created_at)


# ---------- Message ----------

def message_to_domain(model: MessageModel) -> Message:
    """ORM 模型 -> Message 实体；空值/空串统一还原为 None（实体层"无来源"只有一种表示）。"""
    return Message(
        id=model.id,
        conversation_id=model.conversation_id,
        role=MessageRole(model.role),
        content=model.content,
        created_at=model.created_at,
        sources=json.loads(model.sources) if model.sources else None,
    )


def message_to_model(entity: Message) -> MessageModel:
    """Message 实体 -> ORM 模型；sources 序列化为 JSON 文本（中文不转义）。"""
    return MessageModel(
        id=entity.id,
        conversation_id=entity.conversation_id,
        role=entity.role.value,
        content=entity.content,
        created_at=entity.created_at,
        sources=json.dumps(entity.sources, ensure_ascii=False) if entity.sources else None,
    )


# ---------- Document ----------

def document_to_domain(model: DocumentModel) -> Document:
    """ORM 模型 -> Document 实体；status 字符串还原为领域枚举。"""
    return Document(
        id=model.id,
        filename=model.filename,
        file_size=model.file_size,
        status=DocumentStatus(model.status),
        created_at=model.created_at,
    )


def document_to_model(entity: Document) -> DocumentModel:
    """Document 实体 -> ORM 模型；状态以枚举 value 落库。"""
    return DocumentModel(
        id=entity.id,
        filename=entity.filename,
        file_size=entity.file_size,
        status=entity.status.value,
        created_at=entity.created_at,
    )
