"""对话服务测试（真实 SQLite 临时库）。"""

import pytest
import pytest_asyncio

from app.application.services.conversation_service import ConversationNotFoundError, ConversationService
from app.domain.entities.message import MessageRole
from app.infrastructure.database.sqlite.database import SQLiteDatabase


@pytest_asyncio.fixture
async def service(tmp_path) -> ConversationService:
    db = SQLiteDatabase(str(tmp_path / "conv.db"))
    await db.connect()
    await db.init_schema()
    yield ConversationService(db)
    await db.close()


@pytest.mark.asyncio
async def test_create_conversation_with_default_title(service: ConversationService) -> None:
    """空标题应回退为默认标题（前端新建会话场景）。"""
    conversation = await service.create_conversation("  ")
    assert conversation.title == "新对话"
    titled = await service.create_conversation("劳动法咨询")
    assert titled.title == "劳动法咨询"


@pytest.mark.asyncio
async def test_message_roundtrip_and_ordering(service: ConversationService) -> None:
    """问答消息按顺序持久化并可完整恢复。"""
    conversation = await service.create_conversation("咨询")
    await service.add_message(conversation.id, MessageRole.USER, "试用期最长多久？")
    await service.add_message(conversation.id, MessageRole.ASSISTANT, "不超过六个月。")

    messages = await service.get_messages(conversation.id)
    assert [(m.role, m.content) for m in messages] == [
        (MessageRole.USER, "试用期最长多久？"),
        (MessageRole.ASSISTANT, "不超过六个月。"),
    ]


@pytest.mark.asyncio
async def test_add_message_with_sources_roundtrip(service: ConversationService) -> None:
    """带参考来源的助手消息经服务层写入后可完整恢复（FE-023 持久化契约）。"""
    conversation = await service.create_conversation("RAG 咨询")
    sources = [{"source": "劳动合同法.txt", "content": "试用期不得超过六个月。"}]
    await service.add_message(conversation.id, MessageRole.USER, "试用期最长多久？")
    await service.add_message(
        conversation.id, MessageRole.ASSISTANT, "不超过六个月。", sources=sources
    )

    messages = await service.get_messages(conversation.id)
    assert messages[0].sources is None
    assert messages[1].sources == sources


@pytest.mark.asyncio
async def test_operations_on_missing_conversation_raise(service: ConversationService) -> None:
    """对不存在的会话读写/删除都应抛业务异常，防止产生孤儿数据。"""
    with pytest.raises(ConversationNotFoundError):
        await service.get_messages("missing")
    with pytest.raises(ConversationNotFoundError):
        await service.add_message("missing", MessageRole.USER, "问题")
    with pytest.raises(ConversationNotFoundError):
        await service.delete_conversation("missing")


@pytest.mark.asyncio
async def test_delete_conversation_cascades(service: ConversationService) -> None:
    """删除会话后消息一并消失，且列表中不再出现。"""
    c1 = await service.create_conversation("会话1")
    c2 = await service.create_conversation("会话2")
    await service.add_message(c1.id, MessageRole.USER, "问题")

    await service.delete_conversation(c1.id)

    assert [c.id for c in await service.list_conversations()] == [c2.id]
    assert await service.get_messages(c2.id) == []
