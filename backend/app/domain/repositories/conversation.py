"""ConversationRepository 抽象接口。

为什么接口在 domain 层：仓储接口属于领域契约（DDD 仓储模式），
具体由 SQLite/MySQL 在基础设施层实现，业务层只依赖此接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities.conversation import Conversation


class ConversationRepository(ABC):
    """会话仓库契约。"""

    @abstractmethod
    async def create(self, conversation: Conversation) -> Conversation:
        """新建会话并返回带 id 的实体。"""

    @abstractmethod
    async def get(self, conversation_id: str) -> Conversation | None:
        """按 id 查询会话，不存在返回 None。"""

    @abstractmethod
    async def list(self) -> list[Conversation]:
        """列出全部会话（按创建时间倒序，最新的在前）。"""

    @abstractmethod
    async def delete(self, conversation_id: str) -> bool:
        """删除会话，返回是否实际删除。"""
