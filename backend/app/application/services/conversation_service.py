"""对话服务：会话生命周期与消息持久化。

为什么独立成 Service：API 层与 Chat 流程都需要"会话 + 消息"的
组合操作（如删除会话必须级联清理消息），规则只应存在一份；
依赖仅 Database 抽象，与具体存储解耦。
"""

from __future__ import annotations

import logging

from app.domain.entities.conversation import Conversation
from app.domain.entities.message import Message, MessageRole
from app.domain.repositories.database import Database

logger = logging.getLogger("app.conversation.service")

_DEFAULT_TITLE = "新对话"


class ConversationNotFoundError(Exception):
    """指定会话不存在。"""


class ConversationService:
    """会话与消息的业务管理。"""

    def __init__(self, database: Database) -> None:
        self._db = database

    async def create_conversation(self, title: str = "") -> Conversation:
        """创建会话；空标题使用默认标题（前端新建会话场景）。"""
        conversation = await self._db.conversations.create(Conversation(title=title.strip() or _DEFAULT_TITLE))
        logger.info(
            "Conversation created",
            extra={"service": "conversation", "conversation_id": conversation.id, "title": conversation.title},
        )
        return conversation

    async def list_conversations(self) -> list[Conversation]:
        """列出全部会话：按创建时间正序（FE-012：最早创建的在最上面）。

        为什么排序放在应用层（BE-024）：排序是产品展示规则，不是存储职责。
        仓储不输出 SQL ORDER BY，服务层用 sorted 按 created_at 判断顺序——
        这样换任何数据库实现，顺序都不变；也不再依赖 SQLite 专有的 rowid
        作为"同一时刻"的第二排序键（MySQL 没有 rowid）。
        Python 的 sorted 是稳定排序，同一份数据重复查询结果一致。
        """
        conversations = await self._db.conversations.list()
        return sorted(conversations, key=lambda conversation: conversation.created_at)

    async def get_conversation(self, conversation_id: str) -> Conversation:
        """获取会话，不存在时抛出业务异常。"""
        conversation = await self._db.conversations.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(f"会话不存在：{conversation_id}")
        return conversation

    async def get_messages(self, conversation_id: str) -> list[Message]:
        """获取会话全部消息；会话不存在时抛出业务异常。

        消息顺序同样由应用层按 created_at 正序决定（BE-024）：
        提问在上、对应回答在下，与具体数据库的物理返回顺序无关。
        """
        await self.get_conversation(conversation_id)
        messages = await self._db.messages.list_by_conversation(conversation_id)
        return sorted(messages, key=lambda message: message.created_at)

    async def add_message(
        self,
        conversation_id: str,
        role: MessageRole,
        content: str,
        sources: list[dict[str, str]] | None = None,
    ) -> Message:
        """向指定会话追加一条消息；sources 为助手回答的参考来源（可选）。"""
        await self.get_conversation(conversation_id)  # 保证不产生孤儿消息
        return await self._db.messages.add(
            Message(conversation_id=conversation_id, role=role, content=content, sources=sources)
        )

    async def delete_conversation(self, conversation_id: str) -> None:
        """删除会话及其全部消息。"""
        await self.get_conversation(conversation_id)
        removed_messages = await self._db.messages.delete_by_conversation(conversation_id)
        await self._db.conversations.delete(conversation_id)
        logger.info(
            "Conversation deleted",
            extra={
                "service": "conversation",
                "conversation_id": conversation_id,
                "removed_messages": removed_messages,
            },
        )
