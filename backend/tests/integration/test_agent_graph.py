"""LangGraph Agent 工作流测试（BE-015 基础工作流 + BE-016 RAG 工作流）。

用 Fake LLM 与真实 Chroma（确定性 embedding）分别验证：
基础工作流完成一次问答；RAG 工作流把知识库上下文注入 Prompt。
"""

import hashlib

import pytest
import pytest_asyncio

from app.agent.graph import build_qa_graph, run_qa
from app.agent.prompts import LEGAL_SYSTEM_PROMPT
from app.application.services.document_pipeline import DocumentParserFactory, DocumentPipeline
from app.application.services.knowledge_service import KnowledgeIngestionService
from app.application.services.rag_service import RagService
from app.domain.entities.chunk import DocumentChunk
from app.domain.entities.llm import ChatMessage, LlmParams
from app.domain.entities.message import MessageRole
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.services.embedding import EmbeddingService
from app.infrastructure.document_parser.text_parser import TextParser
from app.infrastructure.vector_store.chroma import ChromaVectorStore


class RecordingFakeLLM(LLMProvider):
    """记录收到的消息列表，供断言 Prompt 组装是否符合策略。"""

    def __init__(self, answer: str) -> None:
        self._answer = answer
        self.received: list[list[ChatMessage]] = []

    @property
    def model_name(self) -> str:
        return "fake-model"

    async def chat(self, messages: list[ChatMessage], params: LlmParams | None = None) -> str:
        self.received.append(messages)
        return self._answer

    async def stream(self, messages: list[ChatMessage], params: LlmParams | None = None):
        # 生成节点已统一走 stream，必须在此记录消息供断言
        self.received.append(messages)
        words = self._answer.split(" ")
        for i, word in enumerate(words):
            # 最后一个词不加尾随空格，保证流式拼接与非流式回答逐字符一致
            yield word + (" " if i < len(words) - 1 else "")


class DeterministicEmbedding(EmbeddingService):
    """字符 bigram 哈希词袋向量（与 RAG 测试一致）。"""

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        for i in range(len(text) - 1):
            digest = hashlib.md5(text[i : i + 2].encode("utf-8")).digest()
            vector[digest[0] % self._dim] += 1.0
        return vector

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


# ---- BE-015：基础工作流 ----


@pytest.mark.asyncio
async def test_basic_graph_completes_qa() -> None:
    """基础工作流（无 RAG）应成功执行并产出回答。"""
    llm = RecordingFakeLLM("根据《劳动合同法》，经济补偿按工作年限计算。")
    graph = build_qa_graph(llm, rag=None)
    answer = await run_qa(graph, "经济补偿怎么计算？")
    assert answer.startswith("根据《劳动合同法》")
    # Prompt 应包含法律策略系统消息
    assert llm.received[0][0].content == LEGAL_SYSTEM_PROMPT
    assert llm.received[0][-1].content == "经济补偿怎么计算？"


@pytest.mark.asyncio
async def test_basic_graph_includes_history() -> None:
    """多轮对话历史应被组装进消息列表。"""
    llm = RecordingFakeLLM("好的。")
    graph = build_qa_graph(llm, rag=None)
    history = [
        ChatMessage(role=MessageRole.USER, content="上一问"),
        ChatMessage(role=MessageRole.ASSISTANT, content="上一答"),
    ]
    await run_qa(graph, "继续追问", history=history)
    received = llm.received[0]
    assert [m.content for m in received] == [LEGAL_SYSTEM_PROMPT, "上一问", "上一答", "继续追问"]


# ---- BE-016：RAG 工作流 ----


@pytest_asyncio.fixture
async def rag_graph_factory(tmp_path):
    """构建接入真实 Chroma 知识库的 RAG 工作流。"""
    store = ChromaVectorStore(str(tmp_path / "chroma"))
    await store.initialize()
    embedding = DeterministicEmbedding()
    ingestion = KnowledgeIngestionService(
        DocumentPipeline(parser_factory=DocumentParserFactory([TextParser()])), embedding, store
    )
    await ingestion.ingest_document(
        "doc-1",
        "劳动法问答.txt",
        "劳动合同违约金条款：劳动者违反服务期约定的，应当按照约定向用人单位支付违约金。".encode("utf-8"),
    )
    rag = RagService(embedding, store)

    def factory(llm: LLMProvider):
        return build_qa_graph(llm, rag=rag)

    yield factory
    await store.close()


@pytest.mark.asyncio
async def test_rag_graph_injects_knowledge_context(rag_graph_factory) -> None:
    """RAG 工作流应把知识库内容（含来源标注）注入 Prompt。"""
    llm = RecordingFakeLLM("依据知识库回答。")
    graph = rag_graph_factory(llm)
    answer = await run_qa(graph, "违反服务期约定怎么赔偿")
    assert answer == "依据知识库回答。"
    user_message = llm.received[0][-1].content
    assert "【参考依据】" in user_message
    assert "【来源：劳动法问答.txt】" in user_message
    assert "违约金" in user_message


@pytest.mark.asyncio
async def test_rag_graph_empty_knowledge_marks_no_context(tmp_path) -> None:
    """知识库无命中时，Prompt 不应包含参考依据段（供模型走信息不足策略）。"""
    store = ChromaVectorStore(str(tmp_path / "empty_chroma"))
    await store.initialize()
    llm = RecordingFakeLLM("知识库中暂无相关依据。")
    graph = build_qa_graph(llm, rag=RagService(DeterministicEmbedding(), store))
    try:
        await run_qa(graph, "量子力学的波函数坍缩是什么")
        user_message = llm.received[0][-1].content
        assert "【参考依据】" not in user_message
        assert user_message == "量子力学的波函数坍缩是什么"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_rag_service_min_score_filters_weak_hits(tmp_path) -> None:
    """min_score 过滤：低于阈值的弱命中不应进入上下文（BE-017 信息不足策略的机制）。"""
    store = ChromaVectorStore(str(tmp_path / "weak_chroma"))
    await store.initialize()
    embedding = DeterministicEmbedding()
    content = "劳动合同违约金条款：劳动者违反服务期约定的，应当按照约定向用人单位支付违约金。"
    vectors = await embedding.embed_documents([content])
    await store.add_chunks(
        [DocumentChunk(document_id="doc-1", content=content, metadata={"filename": "劳动法.txt"})],
        vectors,
    )
    # 阈值取 0.99：任何查询都无法达到，等价于"知识库无相关依据"
    strict_rag = RagService(embedding, store, min_score=0.99)
    try:
        context = await strict_rag.build_context("违反服务期约定怎么赔偿")
        assert context == ""
    finally:
        await store.close()

# ---- 流式统一走图 ----


class MultiChunkLLM(RecordingFakeLLM):
    """按固定片段产出，模拟真实 token 流。"""

    async def stream(self, messages: list[ChatMessage], params: LlmParams | None = None):
        self.received.append(messages)
        for part in [self._answer[i : i + 3] for i in range(0, len(self._answer), 3)]:
            yield part


@pytest.mark.asyncio
async def test_graph_astream_custom_emits_llm_tokens() -> None:
    """流式问答必须经由图（astream custom 模式）产出 token，而不是绕过图直连 LLM。"""
    llm = MultiChunkLLM("依据知识库回答。")
    graph = build_qa_graph(llm, rag=None)
    chunks = [chunk async for chunk in graph.astream(
        {"question": "试用期多长？", "history": []}, stream_mode="custom"
    )]
    assert "".join(chunks) == "依据知识库回答。"
    assert len(chunks) > 1  # 逐 token 推送


@pytest.mark.asyncio
async def test_non_stream_invoke_ignores_stream_events() -> None:
    """非流式 ainvoke 与流式走同一节点：answer 完整产出且不受流事件影响。"""
    llm = RecordingFakeLLM("完整回答。")
    graph = build_qa_graph(llm, rag=None)
    answer = await run_qa(graph, "任何问题")
    assert answer == "完整回答。"
