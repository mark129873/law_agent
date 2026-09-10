"""MessageRepository 抽象接口。

DDD 说明：仓储端口只暴露领域需要的查询粒度（list_by_conversation），
不暴露 SQL/索引等存储概念；delete_by_conversation 返回删除条数而非
布尔值，因为"删除了多少条"是业务上关心的结果。
"""

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
        """按会话列出消息。

        契约说明（BE-024）：仓储不承诺消息顺序，对话顺序由应用服务层
        按 created_at 正序决定（提问在前、回答在后）。
        """

    @abstractmethod
    async def delete_by_conversation(self, conversation_id: str) -> int:
        """删除某会话的全部消息，返回删除条数。"""
