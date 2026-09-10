"""SQLAlchemy async Core 的 Database 端口实现。

为什么这样实现（与旧的手写 SQL + aiosqlite 实现的差别）：
1. **方言无关**：建表、DML 全部由 SQLAlchemy Core 依据 schema.py 的
   元数据生成，SQLite 与 MySQL 共用同一份代码，不必维护两套 SQL；
2. **事务语义不变**：仍然由本类独占一条连接，并用事务栈守卫提交边界——
   处于显式事务内时仓库写入不提交，退出最外层事务才提交/回滚，
   保证"要么全部提交、要么全部回滚"（DDD 端口契约不变）；
3. **级联删除由数据库保证**：外键写进表级约束（SQLite 需显式打开
   `PRAGMA foreign_keys`，故在 connect 事件里开关）。

设计模式：本类是领域端口 `Database` 的适配器（Adapter），
三个仓储是 `ConversationRepository` / `MessageRepository` /
`DocumentRepository` 端口的适配器；仓储实例在构造时挂到端口声明的
属性上，上层通过多态使用，可与其他实现（如测试用内存 Fake）互换。
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from types import TracebackType
from typing import Any

from sqlalchemy import delete, event, insert, inspect, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncTransaction, create_async_engine

from app.domain.entities.conversation import Conversation
from app.domain.entities.document import Document, DocumentStatus
from app.domain.entities.message import Message, MessageRole
from app.domain.repositories.conversation import ConversationRepository
from app.domain.repositories.database import Database, TransactionContext
from app.domain.repositories.document import DocumentRepository
from app.domain.repositories.message import MessageRepository
from app.infrastructure.database.sqlalchemy.schema import (
    conversations,
    documents,
    messages,
    metadata,
)

logger = logging.getLogger("app.database.sqlalchemy")


def sqlite_url(db_path: str | Path) -> str:
    """把 SQLite 文件路径转成 SQLAlchemy 异步驱动 URL。

    为什么单独成函数：URL 拼写错误（尤其 Windows 绝对路径的三斜杠写法）
    是最容易犯又最难排查的配置错误，集中一处后容器与测试共用同一实现。
    Windows 路径必须先转 POSIX 形式（`C:\\a\\b.db` -> `C:/a/b.db`），
    否则反斜杠会被当成转义字符。
    """
    return f"sqlite+aiosqlite:///{Path(db_path).as_posix()}"


def _new_id() -> str:
    """生成无业务含义的随机主键。

    为什么不用自增 id：主键由领域层持有后与存储解耦，
    切换 MySQL 或分表时不需要改业务逻辑。
    """
    return uuid.uuid4().hex


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    """SQLite 连接建立后显式打开外键约束。

    为什么必须做：SQLite 默认**关闭**外键，级联删除会静默失效
    （删掉会话却留下孤儿消息）；MySQL 默认开启且无此语句，
    故只在 sqlite 方言上挂监听。
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


def _message_column_names(sync_conn: Connection) -> set[str]:
    """用 SQLAlchemy 反射读取 messages 表的列名（方言无关，替代 PRAGMA）。"""
    return {column["name"] for column in inspect(sync_conn).get_columns("messages")}


class SQLAlchemyDatabase(Database):
    """基于 SQLAlchemy 2.0 async Core 的 Database 实现。

    连接策略：整个应用生命周期持有一条连接（与旧实现一致）。
    为什么暂不引入连接池：端口契约（`transaction()` 挂在数据库实例上）
    与"每请求一连接"的池化模型不兼容，池化属于接入 MySQL 并发时的
    独立改造；当前规模下单连接足够且事务语义最简单。
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._engine: AsyncEngine | None = None
        self._conn: AsyncConnection | None = None
        # 事务栈：非空表示处于显式事务内（栈深即嵌套深度）
        self._tx_stack: list[AsyncTransaction] = []
        # 仓库在构造时即可用，与抽象基类声明的属性对应
        self.conversations = _SqlAlchemyConversationRepository(self)
        self.messages = _SqlAlchemyMessageRepository(self)
        self.documents = _SqlAlchemyDocumentRepository(self)

    # ---------- 生命周期 ----------

    async def connect(self) -> None:
        """创建引擎并建立唯一连接。"""
        engine = create_async_engine(self._url)
        if engine.dialect.name == "sqlite":
            # 监听底层 DBAPI 连接建立时机，保证每条连接都开启外键约束
            event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
        self._engine = engine
        self._conn = await engine.connect()

    async def init_schema(self) -> None:
        """建表 + 轻量迁移，要求幂等（重复调用不报错、不丢数据）。

        `create_all` 默认 checkfirst=True：已存在的表不会被重建，
        因此对既有数据库文件是"零破坏"的；列的增补由下面的迁移负责。
        """
        conn = self._require_conn()
        await conn.run_sync(_create_all)
        await self._migrate_schema()
        await conn.commit()

    async def _migrate_schema(self) -> None:
        """历史库的轻量迁移：为旧 messages 表补齐 sources 列（FE-023）。

        为什么用 ALTER 而不是要求重建库：已有用户的对话数据必须原样保留；
        create_all 不会修改已存在的表，因此对老库检查列缺失后补列是
        唯一幂等路径（列名反射走 SQLAlchemy inspect，方言无关）。
        ALTER TABLE ... ADD COLUMN 在 SQLite 与 MySQL 8 上语法一致。
        """
        conn = self._require_conn()
        columns = await conn.run_sync(_message_column_names)
        if "sources" not in columns:
            await conn.execute(text("ALTER TABLE messages ADD COLUMN sources TEXT"))
            logger.info(
                "Database schema migrated",
                extra={"service": "database", "table": "messages", "column": "sources"},
            )

    async def close(self) -> None:
        """释放连接与引擎资源。"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
        self._tx_stack.clear()

    # ---------- 事务 ----------

    def transaction(self) -> TransactionContext:
        return _SqlAlchemyTransaction(self)

    @property
    def _in_transaction(self) -> bool:
        """是否处于显式事务内（提交边界的唯一判据）。"""
        return bool(self._tx_stack)

    async def _commit(self) -> None:
        """仓库写入后的统一提交入口。

        为什么不能无条件 commit：处于显式事务内时提前提交会破坏
        "全部提交或全部回滚"的原子性，让外层回滚失效；
        只有不在事务内时才允许即时提交。
        """
        if not self._in_transaction:
            await self._require_conn().commit()

    def _require_conn(self) -> AsyncConnection:
        assert self._conn is not None, "必须先调用 connect()"
        return self._conn


def _create_all(sync_conn: Connection) -> None:
    """在同步上下文里建表（AsyncConnection.run_sync 的桥接函数）。"""
    metadata.create_all(sync_conn)


class _SqlAlchemyTransaction(TransactionContext):
    """显式事务上下文：最外层 BEGIN/COMMIT/ROLLBACK，嵌套用 SAVEPOINT。

    为什么显式控制：SQLAlchemy 有 autobegin（一次读也会隐式开启事务），
    若直接再次 `begin()` 会抛 "a transaction is already begun"。
    因此进入最外层事务时优先复用已存在的隐式事务（`get_transaction()`），
    没有才新建；这样"先读后开事务"的调用顺序（如删除会话前先校验存在性）
    也能正常工作。
    """

    def __init__(self, db: SQLAlchemyDatabase) -> None:
        self._db = db
        self._tx: AsyncTransaction | None = None

    async def __aenter__(self) -> None:
        conn = self._db._require_conn()
        if self._db._in_transaction:
            # 嵌套事务：SAVEPOINT 语义，内层回滚不影响外层已完成的写入
            self._tx = await conn.begin_nested()
        else:
            self._tx = conn.get_transaction() or await conn.begin()
        self._db._tx_stack.append(self._tx)
        return await super().__aenter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        self._db._tx_stack.pop()
        if self._tx is not None:
            if exc_type is None:
                await self._tx.commit()
            else:
                # 回滚后事务栈已出栈：最外层回滚会把该事务内全部写入丢弃
                await self._tx.rollback()
        return False


class _SqlAlchemyConversationRepository(ConversationRepository):
    """ConversationRepository 端口的 SQLAlchemy 实现（多态：与内存 Fake 可互换）。"""

    def __init__(self, db: SQLAlchemyDatabase) -> None:
        self._db = db

    async def create(self, conversation: Conversation) -> Conversation:
        conversation.id = conversation.id or _new_id()
        await self._db._require_conn().execute(
            insert(conversations).values(
                id=conversation.id,
                title=conversation.title,
                created_at=conversation.created_at,
            )
        )
        await self._db._commit()
        return conversation

    async def get(self, conversation_id: str) -> Conversation | None:
        result = await self._db._require_conn().execute(
            select(conversations.c.id, conversations.c.title, conversations.c.created_at).where(
                conversations.c.id == conversation_id
            )
        )
        row = result.first()
        if row is None:
            return None
        return Conversation(id=row.id, title=row.title, created_at=row.created_at)

    async def list(self) -> list[Conversation]:
        """列出全部会话。

        注意：这里**不排序**（不输出 SQL ORDER BY）。排序是展示规则，
        由应用服务层按 created_at 统一决定（见 BE-024 与 ARCHITECTURE 第 3 节），
        仓储只保证"把数据取出来"。
        """
        result = await self._db._require_conn().execute(
            select(conversations.c.id, conversations.c.title, conversations.c.created_at)
        )
        return [Conversation(id=row.id, title=row.title, created_at=row.created_at) for row in result]

    async def delete(self, conversation_id: str) -> bool:
        result = await self._db._require_conn().execute(
            delete(conversations).where(conversations.c.id == conversation_id)
        )
        await self._db._commit()
        return result.rowcount > 0


class _SqlAlchemyMessageRepository(MessageRepository):
    """MessageRepository 端口的 SQLAlchemy 实现。

    排序说明：`list_by_conversation` 不做 SQL 排序，消息顺序由
    ConversationService 按 created_at 正序决定（时间之外的物理顺序
    属于存储细节，不能成为业务顺序的依据）。
    """

    def __init__(self, db: SQLAlchemyDatabase) -> None:
        self._db = db

    async def add(self, message: Message) -> Message:
        message.id = message.id or _new_id()
        # 参考来源序列化为 JSON 文本存储（SQLite TEXT / MySQL TEXT 通用）；
        # ensure_ascii=False 保证中文原样可读，便于排查问题
        sources_json = json.dumps(message.sources, ensure_ascii=False) if message.sources else None
        await self._db._require_conn().execute(
            insert(messages).values(
                id=message.id,
                conversation_id=message.conversation_id,
                role=message.role.value,
                content=message.content,
                created_at=message.created_at,
                sources=sources_json,
            )
        )
        await self._db._commit()
        return message

    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        result = await self._db._require_conn().execute(
            select(
                messages.c.id,
                messages.c.conversation_id,
                messages.c.role,
                messages.c.content,
                messages.c.created_at,
                messages.c.sources,
            ).where(messages.c.conversation_id == conversation_id)
        )
        return [
            Message(
                id=row.id,
                conversation_id=row.conversation_id,
                role=MessageRole(row.role),
                content=row.content,
                created_at=row.created_at,
                # 空值/空串统一还原为 None：实体层"无来源"只有一种表示
                sources=json.loads(row.sources) if row.sources else None,
            )
            for row in result
        ]

    async def delete_by_conversation(self, conversation_id: str) -> int:
        result = await self._db._require_conn().execute(
            delete(messages).where(messages.c.conversation_id == conversation_id)
        )
        await self._db._commit()
        return result.rowcount


class _SqlAlchemyDocumentRepository(DocumentRepository):
    """DocumentRepository 端口的 SQLAlchemy 实现（列表不排序，由服务层按时间倒序）。"""

    def __init__(self, db: SQLAlchemyDatabase) -> None:
        self._db = db

    async def create(self, document: Document) -> Document:
        document.id = document.id or _new_id()
        await self._db._require_conn().execute(
            insert(documents).values(
                id=document.id,
                filename=document.filename,
                file_size=document.file_size,
                status=document.status.value,
                created_at=document.created_at,
            )
        )
        await self._db._commit()
        return document

    async def get(self, document_id: str) -> Document | None:
        result = await self._db._require_conn().execute(
            select(
                documents.c.id,
                documents.c.filename,
                documents.c.file_size,
                documents.c.status,
                documents.c.created_at,
            ).where(documents.c.id == document_id)
        )
        row = result.first()
        if row is None:
            return None
        return _row_to_document(row)

    async def list(self) -> list[Document]:
        result = await self._db._require_conn().execute(
            select(
                documents.c.id,
                documents.c.filename,
                documents.c.file_size,
                documents.c.status,
                documents.c.created_at,
            )
        )
        return [_row_to_document(row) for row in result]

    async def delete(self, document_id: str) -> bool:
        result = await self._db._require_conn().execute(
            delete(documents).where(documents.c.id == document_id)
        )
        await self._db._commit()
        return result.rowcount > 0

    async def update_status(self, document_id: str, status: DocumentStatus) -> bool:
        result = await self._db._require_conn().execute(
            documents.update()
            .where(documents.c.id == document_id)
            .values(status=status.value)
        )
        await self._db._commit()
        return result.rowcount > 0


def _row_to_document(row: Any) -> Document:
    """数据库行 -> Document 实体（仓储私有映射，保持领域实体与存储解耦）。"""
    return Document(
        id=row.id,
        filename=row.filename,
        file_size=row.file_size,
        status=DocumentStatus(row.status),
        created_at=row.created_at,
    )
