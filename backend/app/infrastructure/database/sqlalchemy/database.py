"""SQLAlchemy 2.0 async ORM 的 Database 端口实现（BE-025）。

与上一版（Core 表达式 + 裸连接，BE-024）的差别只在 infrastructure 内部：
1. **会话取代裸连接**：改用 `async_sessionmaker` + 单个 `AsyncSession`，
   仍是"进程级一个会话"，不引入连接池（池化会改变 `transaction()` 端口的
   形状，属独立改造）；
2. **仓储改用 ORM 写法**：`session.add()` / `session.get()` / 改属性，
   领域实体与 ORM 模型之间的转换交给 mappers.py（Data Mapper）；
3. **事务语义完全不变**：仍然由事务栈守卫提交边界——处于显式事务内时
   仓储写入不提交，退出最外层事务才提交/回滚，嵌套用 SAVEPOINT，
   保证"要么全部提交、要么全部回滚"（DDD 端口契约不变）。

异步 ORM 的两个关键设置（为什么必须）：
- `expire_on_commit=False`：默认 `True` 会在 commit 后让对象属性过期，
  之后访问属性会触发同步刷新，在 asyncio 下抛 `MissingGreenlet`；
- 不定义 relationship：本项目没有聚合内导航需求，不定义关系就没有
  异步懒加载问题，级联删除由表级外键 `ON DELETE CASCADE` 保证。

设计模式：本类是领域端口 `Database` 的适配器（Adapter）；三个仓储是
Repository 端口的适配器 + 实体/模型映射（Data Mapper）。仓储实例在构造时
挂到端口声明的属性上，上层通过多态使用，可与其他实现（测试用内存 Fake）
互换。
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from types import TracebackType
from typing import Any

from sqlalchemy import delete, event, inspect, select, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    AsyncSessionTransaction,
    async_sessionmaker,
    create_async_engine,
)

from app.domain.entities.conversation import Conversation
from app.domain.entities.document import Document, DocumentStatus
from app.domain.entities.message import Message
from app.domain.repositories.conversation import ConversationRepository
from app.domain.repositories.database import Database, TransactionContext
from app.domain.repositories.document import DocumentRepository
from app.domain.repositories.message import MessageRepository
from app.infrastructure.database.sqlalchemy.mappers import (
    conversation_to_domain,
    conversation_to_model,
    document_to_domain,
    document_to_model,
    message_to_domain,
    message_to_model,
)
from app.infrastructure.database.sqlalchemy.models import (
    Base,
    ConversationModel,
    DocumentModel,
    MessageModel,
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


def _ensure_sqlite_parent_dir(url: str) -> None:
    """建库前保证 SQLite 文件所在目录存在（BE-026 回归修复）。

    ELI5（为什么需要这一步）：SQLite 就像一个只会往**已经存在的抽屉**里放文件的柜子，
    抽屉（`data/` 目录）要是被搬走了，它不会自己造一个，而是直接喊"打不开数据库文件"。
    所以开柜子之前，先确认抽屉在不在，不在就造一个。

    为什么要放在数据库实现里（而不是启动脚本里）：数据目录属于存储细节，
    放在这里后，任何入口（uvicorn、测试脚本、将来的 CLI）都自动获得
    "首次启动自动建库"的能力，不需要每个入口各自记得建目录（否则会重复多份并迟早漏一处）。

    为什么只处理 sqlite：
    - `:memory:` 是内存库，没有磁盘目录可建；
    - MySQL 的 URL 里是库名不是路径，目录由 DBA/部署负责。
    `mkdir(parents=True, exist_ok=True)` 天然幂等——与 init_schema() 的幂等建表同一思路：
    重复调用永远安全。
    """
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        return
    database = parsed.database
    if not database or database == ":memory:":
        return
    # make_url 已把 Windows 绝对路径解析为 "C:/.../law_agent.db" 形式，Path 可直接使用
    parent = Path(database).parent
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Database directory created",
            extra={"service": "database", "directory": str(parent)},
        )


class SQLAlchemyDatabase(Database):
    """基于 SQLAlchemy 2.0 async ORM 的 Database 实现。

    会话策略：整个应用生命周期持有一个 `AsyncSession`（与"单连接"策略等价）。
    为什么暂不引入连接池：端口契约（`transaction()` 挂在数据库实例上）
    与"每请求一个会话/连接"的池化模型不兼容，池化属于接入 MySQL 并发时的
    独立改造；当前规模下单会话足够且事务语义最简单。
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._session: AsyncSession | None = None
        # 事务栈：非空表示处于显式事务内（栈深即嵌套深度）
        self._tx_stack: list[AsyncSessionTransaction] = []
        # 仓库在构造时即可用，与抽象基类声明的属性对应
        self.conversations = _OrmConversationRepository(self)
        self.messages = _OrmMessageRepository(self)
        self.documents = _OrmDocumentRepository(self)

    # ---------- 生命周期 ----------

    async def connect(self) -> None:
        """创建引擎并建立唯一会话。

        建引擎之前先确保 SQLite 文件所在目录存在（BE-026）：干净环境重置
        （删除 backend/data/）后直接启动也不会报 unable to open database file。
        """
        _ensure_sqlite_parent_dir(self._url)
        engine = create_async_engine(self._url)
        if engine.dialect.name == "sqlite":
            # 监听底层 DBAPI 连接建立时机，保证每条连接都开启外键约束
            event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
        self._engine = engine
        # expire_on_commit=False 是异步 ORM 的必要设置（见模块 docstring）
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)
        self._session = self._session_factory()

    async def init_schema(self) -> None:
        """建表 + 轻量迁移，要求幂等（重复调用不报错、不丢数据）。

        `create_all` 默认 checkfirst=True：已存在的表不会被重建，
        因此对既有数据库文件是"零破坏"的；列的增补由下面的迁移负责。
        走会话自己的连接（而不是另开连接）以保持"单连接"语义，
        对文件库与内存库都成立。
        """
        session = self._require_session()
        conn = await session.connection()
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn))
        await self._migrate_schema(conn)
        await session.commit()

    async def _migrate_schema(self, conn: Any) -> None:
        """历史库的轻量迁移：为旧 messages 表补齐 sources 列（FE-023）。

        为什么用 ALTER 而不是要求重建库：已有用户的对话数据必须原样保留；
        create_all 不会修改已存在的表，因此对老库检查列缺失后补列是
        唯一幂等路径（列名反射走 SQLAlchemy inspect，方言无关）。
        ALTER TABLE ... ADD COLUMN 在 SQLite 与 MySQL 8 上语法一致。
        """
        columns = await conn.run_sync(_message_column_names)
        if "sources" not in columns:
            await conn.execute(text("ALTER TABLE messages ADD COLUMN sources TEXT"))
            logger.info(
                "Database schema migrated",
                extra={"service": "database", "table": "messages", "column": "sources"},
            )

    async def close(self) -> None:
        """释放会话与引擎资源。"""
        if self._session is not None:
            await self._session.close()
            self._session = None
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
        self._tx_stack.clear()

    # ---------- 事务 ----------

    def transaction(self) -> TransactionContext:
        return _OrmTransaction(self)

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
            await self._require_session().commit()

    def _require_session(self) -> AsyncSession:
        assert self._session is not None, "必须先调用 connect()"
        return self._session


class _OrmTransaction(TransactionContext):
    """显式事务上下文：最外层 BEGIN/COMMIT/ROLLBACK，嵌套用 SAVEPOINT。

    为什么显式控制：Session 有 autobegin（一次读也会隐式开启事务），
    若直接再次 `begin()` 会抛 "a transaction is already begun"。
    因此进入最外层事务时优先复用已存在的隐式事务（`get_transaction()`），
    没有才新建；这样"先读后开事务"的调用顺序（如删除会话前先校验存在性）
    也能正常工作。
    """

    def __init__(self, db: SQLAlchemyDatabase) -> None:
        self._db = db
        self._tx: AsyncSessionTransaction | None = None

    async def __aenter__(self) -> None:
        session = self._db._require_session()
        if self._db._in_transaction:
            # 嵌套事务：SAVEPOINT 语义，内层回滚不影响外层已完成的写入
            self._tx = await session.begin_nested()
        else:
            self._tx = session.get_transaction() or await session.begin()
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


class _OrmConversationRepository(ConversationRepository):
    """ConversationRepository 端口的 ORM 实现（多态：与内存 Fake 可互换）。"""

    def __init__(self, db: SQLAlchemyDatabase) -> None:
        self._db = db

    async def create(self, conversation: Conversation) -> Conversation:
        conversation.id = conversation.id or _new_id()
        # session.add 后由 commit/flush 落库；主键与时间都由领域层给定，
        # 不需要回读数据库生成的默认值（也就没有异步刷新的坑）
        self._db._require_session().add(conversation_to_model(conversation))
        await self._db._commit()
        return conversation

    async def get(self, conversation_id: str) -> Conversation | None:
        # session.get 走 identity map：同会话内重复取同一主键返回同一对象，
        # 因此"更新后回读"不会读到过期数据
        model = await self._db._require_session().get(ConversationModel, conversation_id)
        return conversation_to_domain(model) if model is not None else None

    async def list(self) -> list[Conversation]:
        """列出全部会话。

        注意：这里**不排序**（不输出 SQL ORDER BY）。排序是展示规则，
        由应用服务层按 created_at 统一决定（见 BE-024 与 ARCHITECTURE 第 3 节），
        仓储只保证"把数据取出来"。
        """
        result = await self._db._require_session().execute(select(ConversationModel))
        return [conversation_to_domain(model) for model in result.scalars().all()]

    async def delete(self, conversation_id: str) -> bool:
        session = self._db._require_session()
        model = await session.get(ConversationModel, conversation_id)
        if model is None:
            return False
        # ORM 属性级删除：外键 ON DELETE CASCADE 负责清理该会话的消息
        await session.delete(model)
        await self._db._commit()
        return True


class _OrmMessageRepository(MessageRepository):
    """MessageRepository 端口的 ORM 实现。

    排序说明：`list_by_conversation` 不做 SQL 排序，消息顺序由
    ConversationService 按 created_at 正序决定（时间之外的物理顺序
    属于存储细节，不能成为业务顺序的依据）。
    """

    def __init__(self, db: SQLAlchemyDatabase) -> None:
        self._db = db

    async def add(self, message: Message) -> Message:
        message.id = message.id or _new_id()
        self._db._require_session().add(message_to_model(message))
        await self._db._commit()
        return message

    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        result = await self._db._require_session().execute(
            select(MessageModel).where(MessageModel.conversation_id == conversation_id)
        )
        return [message_to_domain(model) for model in result.scalars().all()]

    async def delete_by_conversation(self, conversation_id: str) -> int:
        """按会话批量删除消息，返回删除条数。

        为什么这里用批量 DELETE 而不是逐个 ORM 删除：
        1) 端口契约要求返回删除条数，属性级删除拿不到影响行数；
        2) 逐条加载再删除会造成 N+1 次查询。
        `synchronize_session="fetch"` 让 session 与数据库保持一致
        （先查出被删主键并从会话中移除），避免 identity map 残留
        已删除对象导致后续读到脏数据。
        """
        result = await self._db._require_session().execute(
            delete(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .execution_options(synchronize_session="fetch")
        )
        await self._db._commit()
        return result.rowcount


class _OrmDocumentRepository(DocumentRepository):
    """DocumentRepository 端口的 ORM 实现（列表不排序，由服务层按时间倒序）。"""

    def __init__(self, db: SQLAlchemyDatabase) -> None:
        self._db = db

    async def create(self, document: Document) -> Document:
        document.id = document.id or _new_id()
        self._db._require_session().add(document_to_model(document))
        await self._db._commit()
        return document

    async def get(self, document_id: str) -> Document | None:
        model = await self._db._require_session().get(DocumentModel, document_id)
        return document_to_domain(model) if model is not None else None

    async def list(self) -> list[Document]:
        result = await self._db._require_session().execute(select(DocumentModel))
        return [document_to_domain(model) for model in result.scalars().all()]

    async def delete(self, document_id: str) -> bool:
        session = self._db._require_session()
        model = await session.get(DocumentModel, document_id)
        if model is None:
            return False
        await session.delete(model)
        await self._db._commit()
        return True

    async def update_status(self, document_id: str, status: DocumentStatus) -> bool:
        """更新文档状态：取出模型改属性。

        为什么用"改属性"而不是 Core 的批量 UPDATE：文档状态更新后，
        调用方常会紧接着回读同一文档（见 DocumentService 与测试）；
        属性级更新让 identity map 与数据库始终一致，代价是一次额外 SELECT
        ——这是本实现明确接受的取舍（正确性优先于一次查询）。
        """
        session = self._db._require_session()
        model = await session.get(DocumentModel, document_id)
        if model is None:
            return False
        model.status = status.value
        await self._db._commit()
        return True
