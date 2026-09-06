"""数据库抽象基类。

为什么需要 Database 抽象：业务层只应看到"一个可连接、可初始化、
提供三个仓库、支持事务的数据库"，至于是 SQLite 还是 MySQL，
由配置在装配点决定（依赖倒置）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType

from app.domain.repositories.conversation import ConversationRepository
from app.domain.repositories.document import DocumentRepository
from app.domain.repositories.message import MessageRepository


class Database(ABC):
    """数据库抽象：生命周期 + 事务 + 仓库集合。"""

    conversations: ConversationRepository
    messages: MessageRepository
    documents: DocumentRepository

    @abstractmethod
    async def connect(self) -> None:
        """建立连接/初始化驱动资源。"""

    @abstractmethod
    async def init_schema(self) -> None:
        """建表与索引，要求幂等（重复调用不报错不丢数据）。"""

    @abstractmethod
    async def close(self) -> None:
        """释放连接资源。"""

    @abstractmethod
    def transaction(self) -> "TransactionContext":
        """开启一个事务上下文：`async with db.transaction(): ...`。

        事务内通过仓库完成的写入要么全部提交，要么全部回滚。
        """


class TransactionContext(ABC):
    """事务上下文协议，供 `async with` 使用。"""

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        """正常退出提交，异常退出回滚；不吞掉异常（返回 False 继续抛出）。"""
        raise NotImplementedError
