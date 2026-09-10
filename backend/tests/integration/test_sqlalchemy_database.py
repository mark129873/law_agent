"""SQLAlchemy 数据库实现测试（BE-024 迁移后的 SQLite Provider）。

为什么用真实 SQLite 文件测试：本实现的验收标准是"首次启动可以自动
初始化数据库，并能够持久化核心业务数据"，内存 Fake 无法证明持久化、
外键级联与迁移行为，因此这里使用 tmp 目录下的真实数据库文件，
通过 SQLAlchemy 的 sqlite+aiosqlite 驱动访问——与生产路径完全同一套代码。

与迁移前的对应关系：原 test_sqlite_database.py 的断言全部保留，
仅"消息顺序"一项从仓储层移到服务层验证（BE-024：排序职责上移，
仓储不再承诺顺序，见 test_ordering_contract.py）。
"""

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, text

from app.domain.entities.conversation import Conversation
from app.domain.entities.document import Document, DocumentStatus
from app.domain.entities.message import Message, MessageRole
from app.infrastructure.database.sqlalchemy.database import SQLAlchemyDatabase, sqlite_url


@pytest_asyncio.fixture
async def db(tmp_path) -> SQLAlchemyDatabase:
    """每个测试独占一个全新数据库文件，避免用例间数据串扰。"""
    database = SQLAlchemyDatabase(sqlite_url(tmp_path / "test.db"))
    await database.connect()
    await database.init_schema()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_conversation_crud_roundtrip(db: SQLAlchemyDatabase) -> None:
    """会话完整生命周期：创建 -> 查询 -> 列表 -> 删除。"""
    created = await db.conversations.create(Conversation(title="劳动法咨询"))
    assert created.id != ""

    fetched = await db.conversations.get(created.id)
    assert fetched is not None
    assert fetched.title == "劳动法咨询"
    assert fetched.created_at.tzinfo is not None  # 时间戳必须保留时区信息

    await db.conversations.create(Conversation(title="第二个会话"))
    titles = [c.title for c in await db.conversations.list()]
    assert set(titles) == {"劳动法咨询", "第二个会话"}

    assert await db.conversations.delete(created.id) is True
    assert await db.conversations.get(created.id) is None
    assert await db.conversations.delete(created.id) is False


@pytest.mark.asyncio
async def test_messages_persisted_and_cascade_deleted(db: SQLAlchemyDatabase) -> None:
    """消息按会话查询可取回全部；删除会话时消息由外键级联删除。

    注意：仓储层不承诺消息顺序（BE-024），因此这里只断言内容集合与
    "删除会话后不留孤儿消息"；对话顺序由服务层验证。
    """
    conversation = await db.conversations.create(Conversation(title="级联测试"))
    await db.messages.add(
        Message(conversation_id=conversation.id, role=MessageRole.USER, content="第一问")
    )
    await db.messages.add(
        Message(conversation_id=conversation.id, role=MessageRole.ASSISTANT, content="第一答")
    )

    messages = await db.messages.list_by_conversation(conversation.id)
    assert {m.content for m in messages} == {"第一问", "第一答"}
    assert {m.role for m in messages} == {MessageRole.USER, MessageRole.ASSISTANT}

    # 删除会话后消息应被外键级联删除，不留孤儿数据
    await db.conversations.delete(conversation.id)
    assert await db.messages.list_by_conversation(conversation.id) == []


@pytest.mark.asyncio
async def test_document_persist_and_update_status(db: SQLAlchemyDatabase) -> None:
    """文档元数据持久化与状态更新。"""
    doc = await db.documents.create(Document(filename="民法典.pdf", file_size=2048))
    assert await db.documents.update_status(doc.id, DocumentStatus.READY) is True
    fetched = await db.documents.get(doc.id)
    assert fetched is not None
    assert fetched.status is DocumentStatus.READY
    assert fetched.file_size == 2048
    assert await db.documents.delete(doc.id) is True


@pytest.mark.asyncio
async def test_data_persists_across_reconnect(tmp_path) -> None:
    """核心持久化验证：关闭进程级连接后重新打开，数据仍在。"""
    url = sqlite_url(tmp_path / "persist.db")

    first = SQLAlchemyDatabase(url)
    await first.connect()
    await first.init_schema()
    conversation = await first.conversations.create(Conversation(title="跨连接数据"))
    await first.close()

    second = SQLAlchemyDatabase(url)
    await second.connect()
    await second.init_schema()  # 重复建表必须幂等
    fetched = await second.conversations.get(conversation.id)
    assert fetched is not None
    assert fetched.title == "跨连接数据"
    await second.close()


@pytest.mark.asyncio
async def test_message_sources_roundtrip(db: SQLAlchemyDatabase) -> None:
    """参考来源随消息持久化：带 sources 写入后回读一致，无来源消息回读 None。"""
    conversation = await db.conversations.create(Conversation(title="来源测试"))
    sources = [
        {"source": "劳动法.txt", "content": "劳动合同违约金条款……"},
        {"source": "劳动法.txt", "content": "服务期约定条款……"},
    ]
    await db.messages.add(
        Message(conversation_id=conversation.id, role=MessageRole.USER, content="问题")
    )
    await db.messages.add(
        Message(conversation_id=conversation.id, role=MessageRole.ASSISTANT, content="回答", sources=sources)
    )

    messages = await db.messages.list_by_conversation(conversation.id)
    by_role = {m.role: m for m in messages}
    assert by_role[MessageRole.USER].sources is None  # 用户消息无来源
    assert by_role[MessageRole.ASSISTANT].sources == sources  # 来源原样还原（含中文与顺序）


@pytest.mark.asyncio
async def test_schema_migration_adds_sources_column(tmp_path) -> None:
    """旧库迁移：无 sources 列的历史 messages 表在 init_schema 后自动补列且数据保留。

    为什么用同步引擎造旧表：模拟"迁移前版本创建出来的数据库文件"，
    与当前实现（SQLAlchemy）完全解耦；同时验证新实现能直接接管旧库。
    """
    db_path = tmp_path / "legacy.db"
    # 1) 手工构造 FE-023 之前的旧 schema 并写入一条历史消息
    legacy_engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with legacy_engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO messages (id, conversation_id, role, content, created_at) "
                "VALUES ('m1', 'c1', 'assistant', '历史回答', '2026-01-01T00:00:00+00:00')"
            )
        )
    legacy_engine.dispose()

    # 2) 新版本 connect + init_schema：应幂等补齐 sources 列
    database = SQLAlchemyDatabase(sqlite_url(db_path))
    await database.connect()
    await database.init_schema()
    try:
        rows = await database.messages.list_by_conversation("c1")
        assert rows[0].content == "历史回答"
        assert rows[0].sources is None
        assert rows[0].created_at.tzinfo is not None  # 旧库时间同样还原时区

        # 3) 迁移后的表可以正常写入带来源的新消息
        await database.messages.add(
            Message(
                conversation_id="c1",
                role=MessageRole.ASSISTANT,
                content="新回答",
                sources=[{"source": "专利法.txt", "content": "第四十二条……"}],
            )
        )
        rows = await database.messages.list_by_conversation("c1")
        migrated = next(r for r in rows if r.content == "新回答")
        assert migrated.sources == [{"source": "专利法.txt", "content": "第四十二条……"}]

        # 4) 幂等：再次 init_schema 不应报错（列已存在不再 ALTER）
        await database.init_schema()
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_transaction_rollback_with_real_sqlite(db: SQLAlchemyDatabase) -> None:
    """事务异常回滚：事务内写入不应残留到数据库。"""
    conversation = await db.conversations.create(Conversation(title="事务测试"))

    with pytest.raises(RuntimeError):
        async with db.transaction():
            await db.messages.add(
                Message(conversation_id=conversation.id, role=MessageRole.USER, content="应被回滚")
            )
            raise RuntimeError("模拟业务失败")

    assert await db.messages.list_by_conversation(conversation.id) == []


@pytest.mark.asyncio
async def test_transaction_commits_all_writes_at_once(db: SQLAlchemyDatabase) -> None:
    """事务内多次写入在正常退出时一次性提交（原子性的另一半）。"""
    conversation = await db.conversations.create(Conversation(title="提交测试"))

    async with db.transaction():
        await db.messages.add(
            Message(conversation_id=conversation.id, role=MessageRole.USER, content="事务内提问")
        )
        await db.messages.add(
            Message(conversation_id=conversation.id, role=MessageRole.ASSISTANT, content="事务内回答")
        )

    messages = await db.messages.list_by_conversation(conversation.id)
    assert {m.content for m in messages} == {"事务内提问", "事务内回答"}


@pytest.mark.asyncio
async def test_transaction_after_read_does_not_break(db: SQLAlchemyDatabase) -> None:
    """先读后开事务（服务层常见顺序）不应因 autobegin 报错。

    真实场景：ConversationService.delete_conversation 会先 get 校验存在性
    （触发 SQLAlchemy 隐式事务），再进入显式事务；这里锁定该顺序可用。
    """
    conversation = await db.conversations.create(Conversation(title="先读后事务"))
    assert await db.conversations.get(conversation.id) is not None  # 读 -> autobegin

    async with db.transaction():
        await db.messages.add(
            Message(conversation_id=conversation.id, role=MessageRole.USER, content="读后写入")
        )

    assert len(await db.messages.list_by_conversation(conversation.id)) == 1
