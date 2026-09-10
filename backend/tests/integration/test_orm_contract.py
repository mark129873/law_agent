"""ORM 实现特有的契约测试（BE-025）。

为什么单独一个文件：这里锁定的不是"业务行为"（那些在
test_sqlalchemy_database.py 与 test_ordering_contract.py 里），而是
**采用 ORM 之后新增的、容易踩坑的保证**：

1. 仓储出口只能是领域实体，ORM 模型不得越过 infrastructure 边界
   （否则应用层会被 ORM 类型与它的会话状态污染）；
2. `expire_on_commit=False` 生效：commit 之后仍可安全读取 ORM 对象属性
   （默认 True 时属性过期，在异步上下文访问会抛 MissingGreenlet）；
3. identity map 与数据库一致：属性级更新后回读不返回过期状态；
4. 批量删除后 session 内不留已删除对象（脏读防护）；
5. 事务回滚同样能撤销"属性级更新"。
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.domain.entities.conversation import Conversation
from app.domain.entities.document import Document, DocumentStatus
from app.domain.entities.message import Message, MessageRole
from app.infrastructure.database.sqlalchemy.database import SQLAlchemyDatabase, sqlite_url
from app.infrastructure.database.sqlalchemy.models import (
    ConversationModel,
    DocumentModel,
    MessageModel,
)

_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db(tmp_path) -> SQLAlchemyDatabase:
    """独立临时库（SQLite + SQLAlchemy ORM，与生产同一套实现）。"""
    database = SQLAlchemyDatabase(sqlite_url(tmp_path / "orm.db"))
    await database.connect()
    await database.init_schema()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_repositories_return_domain_entities_not_orm_models(db: SQLAlchemyDatabase) -> None:
    """仓储出口必须是领域实体：ORM 模型不越过 infrastructure 边界（DDD 关键约束）。"""
    conversation = await db.conversations.create(Conversation(title="边界检查", created_at=_T0))
    await db.messages.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="问题",
            created_at=_T0,
        )
    )
    document = await db.documents.create(Document(filename="a.txt", file_size=1, created_at=_T0))

    fetched_conversation = await db.conversations.get(conversation.id)
    fetched_messages = await db.messages.list_by_conversation(conversation.id)
    fetched_document = await db.documents.get(document.id)

    # 类型必须精确等于领域 dataclass，且与 ORM 模型类没有任何继承/实例关系
    assert type(fetched_conversation) is Conversation
    assert type(fetched_messages[0]) is Message
    assert type(fetched_document) is Document
    for entity in (fetched_conversation, fetched_messages[0], fetched_document):
        assert not isinstance(entity, (ConversationModel, MessageModel, DocumentModel))
        assert type(entity).__module__.startswith("app.domain")


@pytest.mark.asyncio
async def test_orm_object_readable_after_commit(db: SQLAlchemyDatabase) -> None:
    """expire_on_commit=False：commit 后访问 ORM 对象属性不会抛 MissingGreenlet。

    验证方式：先把会话的 ORM 对象取进 session，再触发一次 commit（写消息），
    然后直接访问该对象的属性——若 expire_on_commit 为默认 True，属性已过期，
    这次访问会在异步上下文里尝试同步刷新并抛 MissingGreenlet。
    """
    conversation = await db.conversations.create(Conversation(title="提交后仍可读", created_at=_T0))
    session = db._require_session()
    model = await session.get(ConversationModel, conversation.id)
    assert model is not None

    # 触发一次 commit（写入消息），使 model 处于"已提交"状态
    await db.messages.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="触发提交",
            created_at=_T0,
        )
    )

    assert model.title == "提交后仍可读"  # 过期属性访问会 MissingGreenlet
    assert model.created_at == _T0
    assert session.sync_session.expire_on_commit is False  # 设置本身也被锁定


@pytest.mark.asyncio
async def test_status_update_is_visible_in_identity_map(db: SQLAlchemyDatabase) -> None:
    """文档状态更新后，同一会话内的对象状态必须同步（不能回读到过期状态）。

    若改用 Core 批量 UPDATE 且不做 session 同步，identity map 里的旧对象
    会原样返回 pending，本用例即会失败——因此它锁定了"属性级更新"这一取舍。
    """
    document = await db.documents.create(
        Document(filename="民法典.pdf", file_size=10, created_at=_T0)
    )
    loaded = await db.documents.get(document.id)
    assert loaded is not None and loaded.status is DocumentStatus.PENDING

    assert await db.documents.update_status(document.id, DocumentStatus.READY) is True

    reloaded = await db.documents.get(document.id)
    assert reloaded is not None and reloaded.status is DocumentStatus.READY


@pytest.mark.asyncio
async def test_bulk_delete_leaves_no_stale_objects_in_session(db: SQLAlchemyDatabase) -> None:
    """批量删除后 session 内不得残留已删除对象（synchronize_session 防护）。"""
    conversation = await db.conversations.create(Conversation(title="批量删除", created_at=_T0))
    for index in range(2):
        await db.messages.add(
            Message(
                conversation_id=conversation.id,
                role=MessageRole.USER,
                content=f"消息{index}",
                created_at=_T0,
            )
        )
    # 先把消息读进 session（填充 identity map）
    assert len(await db.messages.list_by_conversation(conversation.id)) == 2

    removed = await db.messages.delete_by_conversation(conversation.id)

    assert removed == 2
    assert await db.messages.list_by_conversation(conversation.id) == []
    # 会话本身仍在（删除的是消息）
    assert await db.conversations.get(conversation.id) is not None


@pytest.mark.asyncio
async def test_transaction_rollback_reverts_attribute_update(db: SQLAlchemyDatabase) -> None:
    """事务回滚必须撤销"改属性"式更新（ORM 写法的回滚语义验证）。"""
    document = await db.documents.create(
        Document(filename="专利法.txt", file_size=5, created_at=_T0)
    )

    with pytest.raises(RuntimeError):
        async with db.transaction():
            await db.documents.update_status(document.id, DocumentStatus.READY)
            raise RuntimeError("模拟业务失败")

    fetched = await db.documents.get(document.id)
    assert fetched is not None and fetched.status is DocumentStatus.PENDING


@pytest.mark.asyncio
async def test_orm_session_used_by_repositories_is_single_instance(db: SQLAlchemyDatabase) -> None:
    """整个数据库实例持有一个会话（对应"进程级单连接"策略，未引入连接池）。"""
    conversation = await db.conversations.create(Conversation(title="会话唯一性", created_at=_T0))
    await db.messages.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="写入",
            created_at=_T0,
        )
    )

    session = db._require_session()
    # 通过同一个会话查询，能看到上面两次写入（同一会话/连接的直接证据）
    result = await session.execute(
        select(ConversationModel).where(ConversationModel.id == conversation.id)
    )
    assert result.scalars().one().title == "会话唯一性"
