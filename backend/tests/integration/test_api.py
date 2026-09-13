"""API 层集成测试（BE-019/020/021/022）。

测试环境：临时 SQLite + 内存 Fake 向量库 + Fake LLM/Embedding；
覆盖统一错误结构、会话 CRUD、SSE 流式协议、文档上传入库与删除。
"""

import hashlib
import json
from typing import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from app.application.services.rag_service import RagService
from app.containers import create_container
from app.config.settings import Settings
from app.domain.entities.llm import ChatMessage, LlmParams
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.repositories.vector_store import VectorStore
from tests.fakes import InMemoryVectorStore
from app.domain.services.embedding import EmbeddingService
from app.main import create_app


class ScriptedLLM(LLMProvider):
    """脚本化 Fake LLM：按系统提示分流（规划/判分走 chat，生成走 stream）。

    生成答案可经 answer 属性按用例替换；规划默认输出空串
    （节点侧解析失败 → 透传原问题），判分默认输出 pass。
    """

    _JUDGE_PASS = '{"verdict": "pass", "feedback": "", "unsupported": []}'

    def __init__(self, answer: str = "知识库中暂无相关依据，建议咨询专业律师。") -> None:
        self._answer = answer
        self.received_messages: list[list[ChatMessage]] = []

    @property
    def model_name(self) -> str:
        return "scripted-model"

    async def chat(self, messages: list[ChatMessage], params: LlmParams | None = None) -> str:
        self.received_messages.append(messages)
        system = messages[0].content
        from app.agent._legacy.prompts import PLANNER_SYSTEM_PROMPT

        if system == PLANNER_SYSTEM_PROMPT:
            return ""  # 解析失败 → 规划节点透传原问题
        return self._JUDGE_PASS  # 判分（verify 节点）：默认通过

    async def stream(self, messages: list[ChatMessage], params: LlmParams | None = None) -> AsyncIterator[str]:
        self.received_messages.append(messages)
        for part in [self._answer[i : i + 4] for i in range(0, len(self._answer), 4)]:
            yield part


class DeterministicEmbedding(EmbeddingService):
    """字符 bigram 哈希词袋向量。"""

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


@pytest.fixture
def client(tmp_path):
    """构建带临时基础设施与 Fake LLM 的完整应用。

    日志显式指定 INFO + 临时日志目录：让 warning 级别的业务错误日志真正
    流经日志格式化器（extra 键误用会在此暴露），同时不污染 backend/log/。
    """
    settings = Settings(
        sqlite_db_path=str(tmp_path / "api.db"),
        log_dir=str(tmp_path / "log"),
        log_level="INFO",
        _env_file=None,
    )
    app = create_app(settings)
    container = app.state.container
    llm = ScriptedLLM()
    # 在启动前替换 LLM / Embedding / 向量库（避免测试触网与依赖外部 Milvus）：
    # 入库（KnowledgeIngestionService）与检索（RagService）必须用同一个
    # 确定性 embedding，否则向量维度不一致会导致检索报错（曾踩坑）
    embedding = DeterministicEmbedding()
    store = InMemoryVectorStore()
    container.register(LLMProvider, lambda c: llm)
    container.register(EmbeddingService, lambda c: embedding)
    container.register(VectorStore, lambda c: store)
    container.register(
        RagService,
        lambda c: RagService(embedding, c.resolve(VectorStore)),
    )

    with TestClient(app) as test_client:
        test_client.llm = llm  # type: ignore[attr-defined]
        yield test_client


def test_create_and_list_conversations(client: TestClient) -> None:
    """创建会话（含默认标题）并按创建时间正序列出（FE-012：旧在上新在下）。"""
    created = client.post("/api/conversations", json={"title": "劳动法咨询"})
    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "劳动法咨询"

    default = client.post("/api/conversations", json={"title": ""})
    assert default.json()["title"] == "新对话"

    listed = client.get("/api/conversations").json()
    assert [c["title"] for c in listed] == ["劳动法咨询", "新对话"]


def test_messages_and_delete(client: TestClient) -> None:
    """消息查询与级联删除；缺失会话返回统一 404 错误结构。"""
    conversation_id = client.post("/api/conversations", json={"title": "t"}).json()["id"]
    assert client.get(f"/api/conversations/{conversation_id}/messages").json() == []

    deleted = client.delete(f"/api/conversations/{conversation_id}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/conversations/{conversation_id}/messages")
    assert missing.status_code == 404
    assert missing.json()["code"] == 40401


def test_chat_stream_sse_protocol(client: TestClient) -> None:
    """SSE 协议：plan 先行、delta 事件增量到达，done 收尾，完整回答已持久化。

    知识库为空（未上传文档）：不应出现 sources 事件——这是
    "无检索命中 → 无参考文档"的协议契约。
    """
    conversation_id = client.post("/api/conversations", json={"title": "流式"}).json()["id"]

    with client.stream(
        "POST", "/api/chat/stream", json={"conversation_id": conversation_id, "question": "试用期多长？"}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))

    assert events[-1]["type"] == "done"
    assert all(e["type"] != "sources" for e in events)  # 空知识库无来源事件
    assert events[0]["type"] == "plan"  # BE-030：规划事件先行
    assert events[0]["sub_queries"] == ["试用期多长？"]
    deltas = [e["content"] for e in events if e["type"] == "delta"]
    assert "".join(deltas) == "知识库中暂无相关依据，建议咨询专业律师。"

    # 流结束后回答必须已持久化；无检索命中 → 来源为 null
    messages = client.get(f"/api/conversations/{conversation_id}/messages").json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "知识库中暂无相关依据，建议咨询专业律师。"
    assert messages[1]["sources"] is None


def test_chat_stream_emits_sources_and_persists_them(client: TestClient) -> None:
    """RAG 检索有命中：plan→sources→delta 顺序出现，且随回答持久化可回读。"""
    # 上传文档入知识库（测试容器的 RagService 使用确定性 embedding，不触网）
    upload = client.post(
        "/api/documents",
        files={"file": ("劳动法.txt", "劳动合同违约金条款：违反服务期约定应支付违约金。".encode("utf-8"))},
    )
    assert upload.status_code == 201
    # 有依据场景的生成答案须满足校验契约（注明来源），否则 verify 会打回重生成
    client.llm._answer = "依据知识库：试用期最长不超过六个月。【来源：劳动法.txt】"  # type: ignore[attr-defined]

    conversation_id = client.post("/api/conversations", json={"title": "来源流"}).json()["id"]
    with client.stream(
        "POST", "/api/chat/stream", json={"conversation_id": conversation_id, "question": "违反服务期约定怎么赔偿"}
    ) as response:
        assert response.status_code == 200
        events = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))

    sources_events = [e for e in events if e["type"] == "sources"]
    assert len(sources_events) == 1  # 最多一次
    # sources 先于第一个 delta 到达（检索节点先于生成节点执行）
    first_delta_index = events.index(next(e for e in events if e["type"] == "delta"))
    assert events.index(sources_events[0]) < first_delta_index
    source_items = sources_events[0]["sources"]
    assert source_items and source_items[0]["source"] == "劳动法.txt"
    assert "违约金" in source_items[0]["content"]

    # 来源随回答持久化：历史消息接口原样返回，前端刷新后仍可展示参考文档
    messages = client.get(f"/api/conversations/{conversation_id}/messages").json()
    assert messages[0]["sources"] is None  # 用户消息无来源
    assert messages[1]["sources"] == source_items


def test_chat_stream_missing_conversation_404(client: TestClient) -> None:
    """不存在的会话应在进入流之前返回 404，而不是开始 SSE。"""
    response = client.post("/api/chat/stream", json={"conversation_id": "missing", "question": "q"})
    assert response.status_code == 404


def test_document_upload_ingests_and_deletes(client: TestClient) -> None:
    """上传 TXT → 状态 ready → 列表可见 → 删除后消失。"""
    upload = client.post(
        "/api/documents",
        files={"file": ("劳动法.txt", "劳动合同违约金条款：违反服务期约定应支付违约金。".encode("utf-8"))},
    )
    assert upload.status_code == 201
    body = upload.json()
    assert body["status"] == "ready"
    assert body["filename"] == "劳动法.txt"

    assert [d["id"] for d in client.get("/api/documents").json()] == [body["id"]]

    deleted = client.delete(f"/api/documents/{body['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/documents").json() == []


def test_document_upload_rejects_unsupported_format(client: TestClient) -> None:
    """不支持的格式返回 400 统一错误结构。"""
    response = client.post("/api/documents", files={"file": ("virus.exe", b"MZ...")})
    assert response.status_code == 400
    assert response.json()["code"] == 40001


def test_validation_error_unified_shape(client: TestClient) -> None:
    """请求参数校验失败应返回统一错误结构（而不是默认 422 形状）。"""
    response = client.post("/api/chat/stream", json={"conversation_id": "c"})
    assert response.status_code == 400
    assert response.json()["code"] == 40002


def test_request_id_header_is_generated_and_forwarded(client: TestClient) -> None:
    """每个响应都带 x-request-id；请求头传入时原样沿用（便于跨服务追踪）。"""
    generated = client.get("/api/health")
    assert generated.status_code == 200
    assert generated.headers.get("x-request-id")  # 缺省自动生成

    forwarded = client.get("/api/health", headers={"X-Request-ID": "trace-abc"})
    assert forwarded.headers["x-request-id"] == "trace-abc"
