"""SQLite 数据库实现。

为什么放在 infrastructure 层：这里所有代码都只关心 SQLite 的细节
（SQL 方言、PRAGMA、事务语句），上层业务永远看不到这些内容；
未来 MySQL 实现与本文件平级，业务层零感知。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from types import TracebackType

import aiosqlite

from app.domain.entities.conversation import Conversation
from app.domain.entities.document import Document, DocumentStatus
from app.domain.entities.message import Message, MessageRole
from app.domain.repositories.database import Database, TransactionContext
from app.domain.repositories.conversation import ConversationRepository
from app.domain.repositories.document import DocumentRepository
from app.domain.repositories.message import MessageRepository


def _new_id() -> str:
    """生成无业务含义的随机主键。

    为什么不用自增 id：主键由领域层持有后与存储解耦，
    未来切换 MySQL 或分表时不需要改业务逻辑。
    """
    return uuid.uuid4().hex


def _to_iso(value: datetime) -> str:
    """datetime 转 ISO 字符串存储。"""
    return value.isoformat()


def _from_iso(value: str) -> datetime:
    """ISO 字符串还原 datetime（SQLite 中时间以 TEXT 存储）。"""
    return datetime.fromisoformat(value)


class SQLiteDatabase(Database):
    """基于 aiosqlite 的 Database 抽象实现。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None
        # 显式事务嵌套深度：>0 时仓库的写入不自动提交，
        # 提交边界统一由最外层事务上下文控制（见 _commit）
        self._tx_depth = 0
        # 仓库实例在 connect 后即可用，与抽象基类声明的属性对应
        self.conversations = _SQLiteConversationRepository(self)
        self.messages = _SQLiteMessageRepository(self)
        self.documents = _SQLiteDocumentRepository(self)

    async def _commit(self) -> None:
        """仓库写入后的统一提交入口。

        为什么不能无条件 commit：处于显式事务内时提前提交会破坏
        "全部提交或全部回滚"的原子性，让外层 ROLLBACK 失效；
        只有不在事务内时才允许即时提交。
        """
        if self._tx_depth == 0:
            await self._require_conn().commit()

    async def connect(self) -> None:
        # 父目录可能不存在（首次启动），先创建保证连接成功
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        # 级联删除依赖外键约束，而 SQLite 默认关闭外键，必须显式开启
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.commit()

    async def init_schema(self) -> None:
        """建表与索引；IF NOT EXISTS 保证重复调用幂等。"""
        assert self._conn is not None, "必须先调用 connect()"
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id);
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def transaction(self) -> TransactionContext:
        return _SQLiteTransaction(self)

    def _require_conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "必须先调用 connect()"
        return self._conn


class _SQLiteTransaction(TransactionContext):
    """显式 BEGIN/COMMIT/ROLLBACK 事务。

    为什么显式控制：Python sqlite3 的隐式事务行为跨版本有差异，
    显式语句让回滚语义在测试与生产中保持一致。
    """

    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    async def __aenter__(self) -> None:
        # 嵌套事务复用最外层事务（SAVEPOINT 语义本版暂不需要）
        if self._db._tx_depth == 0:
            await self._db._require_conn().execute("BEGIN")
        self._db._tx_depth += 1
        return await super().__aenter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        conn = self._db._require_conn()
        self._db._tx_depth -= 1
        if exc_type is None:
            # 只在最外层事务结束时真正提交
            if self._db._tx_depth == 0:
                await conn.commit()
        else:
            await conn.execute("ROLLBACK")
            self._db._tx_depth = 0
        return False


class _SQLiteConversationRepository(ConversationRepository):
    """ConversationRepository 端口的 SQLite 实现（多态：与内存 Fake 可互换）。"""
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    async def create(self, conversation: Conversation) -> Conversation:
        conversation.id = conversation.id or _new_id()
        await self._db._require_conn().execute(
            "INSERT INTO conversations (id, title, created_at) VALUES (?, ?, ?)",
            (conversation.id, conversation.title, _to_iso(conversation.created_at)),
        )
        await self._db._commit()
        return conversation

    async def get(self, conversation_id: str) -> Conversation | None:
        async with self._db._require_conn().execute(
            "SELECT id, title, created_at FROM conversations WHERE id = ?",
            (conversation_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return Conversation(id=row[0], title=row[1], created_at=_from_iso(row[2]))

    async def list(self) -> list[Conversation]:
        async with self._db._require_conn().execute(
            "SELECT id, title, created_at FROM conversations ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
        return [Conversation(id=r[0], title=r[1], created_at=_from_iso(r[2])) for r in rows]

    async def delete(self, conversation_id: str) -> bool:
        cursor = await self._db._require_conn().execute(
            "DELETE FROM conversations WHERE id = ?", (conversation_id,)
        )
        await self._db._commit()
        return cursor.rowcount > 0


class _SQLiteMessageRepository(MessageRepository):
    """MessageRepository 端口的 SQLite 实现。

    list_by_conversation 以 created_at + rowid 双键排序：
    同毫秒创建的消息按插入顺序稳定输出，保证对话顺序可复现。
    """
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    async def add(self, message: Message) -> Message:
        message.id = message.id or _new_id()
        await self._db._require_conn().execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                message.id,
                message.conversation_id,
                message.role.value,
                message.content,
                _to_iso(message.created_at),
            ),
        )
        await self._db._commit()
        return message

    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        async with self._db._require_conn().execute(
            "SELECT id, conversation_id, role, content, created_at FROM messages "
            "WHERE conversation_id = ? ORDER BY created_at ASC, rowid ASC",
            (conversation_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            Message(
                id=r[0],
                conversation_id=r[1],
                role=MessageRole(r[2]),
                content=r[3],
                created_at=_from_iso(r[4]),
            )
            for r in rows
        ]

    async def delete_by_conversation(self, conversation_id: str) -> int:
        cursor = await self._db._require_conn().execute(
            "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
        )
        await self._db._commit()
        return cursor.rowcount


class _SQLiteDocumentRepository(DocumentRepository):
    """DocumentRepository 端口的 SQLite 实现。"""
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    async def create(self, document: Document) -> Document:
        document.id = document.id or _new_id()
        await self._db._require_conn().execute(
            "INSERT INTO documents (id, filename, file_size, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                document.id,
                document.filename,
                document.file_size,
                document.status.value,
                _to_iso(document.created_at),
            ),
        )
        await self._db._commit()
        return document

    async def get(self, document_id: str) -> Document | None:
        async with self._db._require_conn().execute(
            "SELECT id, filename, file_size, status, created_at FROM documents WHERE id = ?",
            (document_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_document(row)

    async def list(self) -> list[Document]:
        async with self._db._require_conn().execute(
            "SELECT id, filename, file_size, status, created_at FROM documents ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_document(r) for r in rows]

    async def delete(self, document_id: str) -> bool:
        cursor = await self._db._require_conn().execute(
            "DELETE FROM documents WHERE id = ?", (document_id,)
        )
        await self._db._commit()
        return cursor.rowcount > 0

    async def update_status(self, document_id: str, status: DocumentStatus) -> bool:
        cursor = await self._db._require_conn().execute(
            "UPDATE documents SET status = ? WHERE id = ?", (status.value, document_id)
        )
        await self._db._commit()
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_document(row: tuple) -> Document:
        return Document(
            id=row[0],
            filename=row[1],
            file_size=row[2],
            status=DocumentStatus(row[3]),
            created_at=_from_iso(row[4]),
        )
