"""数据库抽象层测试。

为什么这样测试：BE-004 的验收标准是"业务层通过数据库抽象接口访问数据，
后续可以增加 MySQL 实现而无需修改业务层"。因此用一个与 SQLite 完全无关的
内存 Fake 实现跑通业务流程，证明业务代码只依赖 Database 抽象；
BE-005 的 SQLite 实现将复用同一套契约测试的写法。
"""

from datetime import datetime

import pytest

from app.domain.entities.conversation import Conversation
from app.domain.entities.document import Document, DocumentStatus
from app.domain.entities.message import Message, MessageRole
from app.domain.repositories.database import Database, TransactionContext
from app.domain.repositories.conversation import ConversationRepository
from app.domain.repositories.document import DocumentRepository
from app.domain.repositories.message import MessageRepository


class InMemoryDatabase(Database):
    """内存 Fake 实现：与 SQLite/MySQL 无任何关系，只履行 Database 契约。

    为什么不持久化到磁盘：本测试关注接口契约与业务解耦，
    持久化行为属于 BE-005 具体实现的职责。
    """

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}
        self._messages: list[Message] = []
        self._documents: dict[str, Document] = {}
        self.conversations = _FakeConversationRepository(self)
        self.messages = _FakeMessageRepository(self)
        self.documents = _FakeDocumentRepository(self)

    async def connect(self) -> None: ...
    async def init_schema(self) -> None: ...
    async def close(self) -> None: ...

    def transaction(self) -> TransactionContext:
        return _FakeTransaction(self)


class _FakeTransaction(TransactionContext):
    """简单事务：异常时回滚本次上下文内的写入。"""

    def __init__(self, db: InMemoryDatabase) -> None:
        self._db = db
        self._messages_snapshot: list[Message] | None = None

    async def __aenter__(self) -> None:
        self._messages_snapshot = list(self._db._messages)
        return await super().__aenter__()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            assert self._messages_snapshot is not None
            self._db._messages[:] = self._messages_snapshot
        return False


class _FakeConversationRepository(ConversationRepository):
    def __init__(self, db: InMemoryDatabase) -> None:
        self._db = db

    async def create(self, conversation: Conversation) -> Conversation:
        conversation.id = conversation.id or f"c{len(self._db._conversations) + 1}"
        self._db._conversations[conversation.id] = conversation
        return conversation

    async def get(self, conversation_id: str) -> Conversation | None:
        return self._db._conversations.get(conversation_id)

    async def list(self) -> list[Conversation]:
        return sorted(self._db._conversations.values(), key=lambda c: c.created_at, reverse=True)

    async def delete(self, conversation_id: str) -> bool:
        return self._db._conversations.pop(conversation_id, None) is not None


class _FakeMessageRepository(MessageRepository):
    def __init__(self, db: InMemoryDatabase) -> None:
        self._db = db

    async def add(self, message: Message) -> Message:
        message.id = message.id or f"m{len(self._db._messages) + 1}"
        self._db._messages.append(message)
        return message

    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        return [m for m in self._db._messages if m.conversation_id == conversation_id]

    async def delete_by_conversation(self, conversation_id: str) -> int:
        before = len(self._db._messages)
        self._db._messages[:] = [m for m in self._db._messages if m.conversation_id != conversation_id]
        return before - len(self._db._messages)


class _FakeDocumentRepository(DocumentRepository):
    def __init__(self, db: InMemoryDatabase) -> None:
        self._db = db

    async def create(self, document: Document) -> Document:
        document.id = document.id or f"d{len(self._db._documents) + 1}"
        self._db._documents[document.id] = document
        return document

    async def get(self, document_id: str) -> Document | None:
        return self._db._documents.get(document_id)

    async def list(self) -> list[Document]:
        return sorted(self._db._documents.values(), key=lambda d: d.created_at, reverse=True)

    async def delete(self, document_id: str) -> bool:
        return self._db._documents.pop(document_id, None) is not None

    async def update_status(self, document_id: str, status: DocumentStatus) -> bool:
        document = self._db._documents.get(document_id)
        if document is None:
            return False
        document.status = status
        return True


async def run_chat_business_flow(db: Database, question: str, answer: str) -> list[Message]:
    """典型业务流程：创建会话、保存问答、读取历史。

    为什么写成普通函数：模拟未来的 ChatService ——
    注意其参数类型只有 Database 抽象，未出现任何具体实现。
    """
    conversation = await db.conversations.create(Conversation(title="测试会话"))
    await db.messages.add(Message(conversation_id=conversation.id, role=MessageRole.USER, content=question))
    await db.messages.add(Message(conversation_id=conversation.id, role=MessageRole.ASSISTANT, content=answer))
    return await db.messages.list_by_conversation(conversation.id)


@pytest.mark.asyncio
async def test_business_flow_runs_against_abstraction() -> None:
    """业务流程在内存 Fake 上完整跑通，证明其不依赖具体数据库。"""
    db = InMemoryDatabase()
    messages = await run_chat_business_flow(db, "劳动合同违约怎么办？", "根据劳动合同法…")
    assert [m.role for m in messages] == [MessageRole.USER, MessageRole.ASSISTANT]
    assert messages[0].content == "劳动合同违约怎么办？"


@pytest.mark.asyncio
async def test_conversation_delete_removes_session_only() -> None:
    """删除会话后 get 应返回 None，其他会话不受影响。"""
    db = InMemoryDatabase()
    c1 = await db.conversations.create(Conversation(title="会话1"))
    c2 = await db.conversations.create(Conversation(title="会话2"))
    assert await db.conversations.delete(c1.id) is True
    assert await db.conversations.get(c1.id) is None
    assert await db.conversations.get(c2.id) is not None
    assert await db.conversations.delete("不存在") is False


@pytest.mark.asyncio
async def test_document_status_lifecycle() -> None:
    """文档状态机：pending -> ready；不存在的文档更新返回 False。"""
    db: Database = InMemoryDatabase()
    doc = await db.documents.create(Document(filename="劳动法.pdf", file_size=1024))
    assert doc.status is DocumentStatus.PENDING
    assert await db.documents.update_status(doc.id, DocumentStatus.READY) is True
    assert (await db.documents.get(doc.id)).status is DocumentStatus.READY
    assert await db.documents.update_status("不存在", DocumentStatus.READY) is False


@pytest.mark.asyncio
async def test_transaction_rolls_back_on_error() -> None:
    """事务内抛异常时，事务内的写入应被回滚。"""
    db = InMemoryDatabase()
    with pytest.raises(RuntimeError):
        async with db.transaction():
            await db.messages.add(
                Message(conversation_id="c1", role=MessageRole.USER, content="会被回滚")
            )
            raise RuntimeError("业务失败")
    assert await db.messages.list_by_conversation("c1") == []
