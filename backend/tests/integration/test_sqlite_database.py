"""SQLite 数据库实现测试。

为什么用真实 SQLite 文件测试：BE-005 的验收标准是"首次启动可以自动
初始化 SQLite 数据库，并能够持久化核心业务数据"，内存 Fake 无法证明
持久化与外键级联行为，因此这里使用 tmp 目录下的真实数据库文件。
"""

import pytest
import pytest_asyncio

from app.domain.entities.conversation import Conversation
from app.domain.entities.document import Document, DocumentStatus
from app.domain.entities.message import Message, MessageRole
from app.infrastructure.database.sqlite.database import SQLiteDatabase


@pytest_asyncio.fixture
async def db(tmp_path):
    """每个测试独占一个全新数据库文件，避免用例间数据串扰。"""
    database = SQLiteDatabase(str(tmp_path / "test.db"))
    await database.connect()
    await database.init_schema()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_conversation_crud_roundtrip(db: SQLiteDatabase) -> None:
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
async def test_messages_ordered_and_cascade_deleted(db: SQLiteDatabase) -> None:
    """消息按会话查询保持顺序；删除会话时消息级联删除。"""
    conversation = await db.conversations.create(Conversation(title="级联测试"))
    await db.messages.add(
        Message(conversation_id=conversation.id, role=MessageRole.USER, content="第一问")
    )
    await db.messages.add(
        Message(conversation_id=conversation.id, role=MessageRole.ASSISTANT, content="第一答")
    )

    messages = await db.messages.list_by_conversation(conversation.id)
    assert [m.content for m in messages] == ["第一问", "第一答"]
    assert messages[0].role is MessageRole.USER

    # 删除会话后消息应被外键级联删除，不留孤儿数据
    await db.conversations.delete(conversation.id)
    assert await db.messages.list_by_conversation(conversation.id) == []


@pytest.mark.asyncio
async def test_document_persist_and_update_status(db: SQLiteDatabase) -> None:
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
    db_path = str(tmp_path / "persist.db")

    first = SQLiteDatabase(db_path)
    await first.connect()
    await first.init_schema()
    conversation = await first.conversations.create(Conversation(title="跨连接数据"))
    await first.close()

    second = SQLiteDatabase(db_path)
    await second.connect()
    await second.init_schema()  # 重复建表必须幂等
    fetched = await second.conversations.get(conversation.id)
    assert fetched is not None
    assert fetched.title == "跨连接数据"
    await second.close()


@pytest.mark.asyncio
async def test_transaction_rollback_with_real_sqlite(db: SQLiteDatabase) -> None:
    """事务异常回滚：事务内写入不应残留到数据库。"""
    conversation = await db.conversations.create(Conversation(title="事务测试"))

    with pytest.raises(RuntimeError):
        async with db.transaction():
            await db.messages.add(
                Message(conversation_id=conversation.id, role=MessageRole.USER, content="应被回滚")
            )
            raise RuntimeError("模拟业务失败")

    assert await db.messages.list_by_conversation(conversation.id) == []
