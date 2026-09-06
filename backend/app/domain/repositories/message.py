"""MessageRepository 抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities.message import Message


class MessageRepository(ABC):
    """消息仓库契约。"""

    @abstractmethod
    async def add(self, message: Message) -> Message:
        """保存消息并返回带 id 的实体。"""

    @abstractmethod
    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        """按会话列出消息（按创建时间正序，保持对话顺序）。"""

    @abstractmethod
    async def delete_by_conversation(self, conversation_id: str) -> int:
        """删除某会话的全部消息，返回删除条数。"""
