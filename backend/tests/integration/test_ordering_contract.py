"""列表排序契约测试（BE-024：排序职责上移到应用服务层，仅按创建时间判断）。

为什么单独一个测试文件：本文件锁定的是"排序规则住在哪一层"这一架构契约。
仓储（数据库实现）不承诺顺序，服务层按 created_at 决定顺序；
因此这里**故意乱序落库**（先写时间较晚的、后写时间较早的），
如果排序仍然依赖插入顺序或数据库物理行号，这些用例就会失败。
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.application.services.conversation_service import ConversationService
from app.application.services.document_pipeline import DocumentParserFactory
from app.application.services.document_service import DocumentService
from app.domain.entities.conversation import Conversation
from app.domain.entities.document import Document
from app.domain.entities.message import Message, MessageRole
from app.infrastructure.database.sqlalchemy.database import SQLAlchemyDatabase, sqlite_url

# 统一时间基准：所有用例显式指定 created_at，不依赖真实时钟
_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class _NoopIngestion:
    """入库桩：排序测试不触发解析与向量化，只用到 Database。"""

    async def ingest_document(self, document_id: str, filename: str, content: bytes) -> list[str]:
        return []


class _NoopVectorStore:
    """向量库桩：排序测试不涉及向量读写。"""

    async def delete_by_document(self, document_id: str) -> int:
        return 0


@pytest_asyncio.fixture
async def db(tmp_path) -> SQLAlchemyDatabase:
    """独立临时库（SQLite + SQLAlchemy，与生产同一套实现）。"""
    database = SQLAlchemyDatabase(sqlite_url(tmp_path / "ordering.db"))
    await database.connect()
    await database.init_schema()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def conversation_service(db: SQLAlchemyDatabase) -> ConversationService:
    return ConversationService(db)


@pytest_asyncio.fixture
async def document_service(db: SQLAlchemyDatabase) -> DocumentService:
    """文档服务：解析器用真实工厂（无 IO），入库与向量库用桩。"""
    return DocumentService(
        database=db,
        parser_factory=DocumentParserFactory([]),
        ingestion_service=_NoopIngestion(),  # type: ignore[arg-type]  # 测试桩，鸭子类型
        vector_store=_NoopVectorStore(),  # type: ignore[arg-type]  # 测试桩，鸭子类型
    )


@pytest.mark.asyncio
async def test_conversations_sorted_by_created_at_ascending(
    db: SQLAlchemyDatabase, conversation_service: ConversationService
) -> None:
    """会话列表按创建时间正序：即使"较早的会话"是后写入的，也要排在最前。"""
    # 乱序写入：先写较晚的时间，再写较早的时间
    later = await db.conversations.create(Conversation(title="较晚", created_at=_T0 + timedelta(minutes=5)))
    earlier = await db.conversations.create(Conversation(title="较早", created_at=_T0))
    middle = await db.conversations.create(Conversation(title="居中", created_at=_T0 + timedelta(minutes=2)))

    titles = [c.title for c in await conversation_service.list_conversations()]
    assert titles == ["较早", "居中", "较晚"]
    assert [c.id for c in await conversation_service.list_conversations()] == [
        earlier.id,
        middle.id,
        later.id,
    ]


@pytest.mark.asyncio
async def test_messages_sorted_by_created_at_ascending(
    db: SQLAlchemyDatabase, conversation_service: ConversationService
) -> None:
    """会话消息按创建时间正序：后写入但时间更早的消息排在最前（提问在上、回答在下）。"""
    conversation = await db.conversations.create(Conversation(title="乱序消息", created_at=_T0))
    # 先写"回答"（时间较晚），再写"提问"（时间较早）
    await db.messages.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="回答",
            created_at=_T0 + timedelta(seconds=30),
        )
    )
    await db.messages.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="提问",
            created_at=_T0,
        )
    )

    messages = await conversation_service.get_messages(conversation.id)
    assert [(m.role, m.content) for m in messages] == [
        (MessageRole.USER, "提问"),
        (MessageRole.ASSISTANT, "回答"),
    ]


@pytest.mark.asyncio
async def test_documents_sorted_by_created_at_descending(
    db: SQLAlchemyDatabase, document_service: DocumentService
) -> None:
    """文档列表按上传时间倒序：即使最新的文档是先写入的，也要排在最前。"""
    await db.documents.create(Document(filename="最新.pdf", file_size=1, created_at=_T0 + timedelta(hours=1)))
    await db.documents.create(Document(filename="最旧.pdf", file_size=1, created_at=_T0))
    await db.documents.create(Document(filename="居中.pdf", file_size=1, created_at=_T0 + timedelta(minutes=30)))

    filenames = [d.filename for d in await document_service.list_documents()]
    assert filenames == ["最新.pdf", "居中.pdf", "最旧.pdf"]


@pytest.mark.asyncio
async def test_same_timestamp_order_is_stable_and_complete(
    db: SQLAlchemyDatabase, conversation_service: ConversationService
) -> None:
    """创建时间完全相同时：不引入物理行号之类第二排序键，但结果必须稳定且不丢数据。

    这是 BE-024 的明确取舍：排序**只**依据时间。同一时刻的记录顺序
    由底层返回顺序决定（不再依赖 SQLite 的 rowid），因此这里只锁定
    "两次查询结果一致 + 数据完整"，不锁定具体先后。
    """
    for index in range(3):
        await db.conversations.create(Conversation(title=f"同一时刻-{index}", created_at=_T0))

    first = [c.id for c in await conversation_service.list_conversations()]
    second = [c.id for c in await conversation_service.list_conversations()]

    assert len(first) == 3
    assert set(first) == set(second)
    assert first == second  # 稳定：同一份数据重复查询顺序一致
