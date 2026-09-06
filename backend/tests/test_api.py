"""API 层集成测试（BE-019/020/021/022）。

测试环境：临时 SQLite + 临时 Chroma + Fake LLM/Embedding；
覆盖统一错误结构、会话 CRUD、SSE 流式协议、文档上传入库与删除。
"""

import hashlib
import json
from typing import AsyncIterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from app.application.services.rag_service import RagService
from app.containers import create_container
from app.config.settings import Settings
from app.domain.entities.llm import ChatMessage, LlmParams
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.repositories.vector_store import VectorStore
from app.domain.services.embedding import EmbeddingService
from app.main import create_app


class ScriptedLLM(LLMProvider):
    """脚本化 Fake LLM：chat 返回固定答案，stream 按词产出。"""

    def __init__(self, answer: str = "依据知识库：试用期最长不超过六个月。") -> None:
        self._answer = answer
        self.received_messages: list[list[ChatMessage]] = []

    @property
    def model_name(self) -> str:
        return "scripted-model"

    async def chat(self, messages: list[ChatMessage], params: LlmParams | None = None) -> str:
        self.received_messages.append(messages)
        return self._answer

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
def client(tmp_path, monkeypatch):
    """构建带临时基础设施与 Fake LLM 的完整应用。

    LOG_LEVEL=INFO：让 warning 级别的业务错误日志真正流经日志格式化器，
    保证 extra 键误用（如占用 LogRecord 保留字段）在测试期就暴露。
    """
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    from app.common.logging import setup_logging

    setup_logging()

    settings = Settings(
        sqlite_db_path=str(tmp_path / "api.db"),
        chroma_persist_dir=str(tmp_path / "chroma"),
        _env_file=None,
    )
    app = create_app(settings)
    container = app.state.container
    llm = ScriptedLLM()
    # 在启动前替换 LLM 与 RAG 检索（避免测试触网）
    container.register(LLMProvider, lambda c: llm)
    container.register(RagService, lambda c: RagService(DeterministicEmbedding(), c.resolve(VectorStore)))

    with TestClient(app) as test_client:
        test_client.llm = llm  # type: ignore[attr-defined]
        yield test_client


def test_create_and_list_conversations(client: TestClient) -> None:
    """创建会话（含默认标题）并按时间倒序列出。"""
    created = client.post("/api/conversations", json={"title": "劳动法咨询"})
    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "劳动法咨询"

    default = client.post("/api/conversations", json={"title": ""})
    assert default.json()["title"] == "新对话"

    listed = client.get("/api/conversations").json()
    assert [c["title"] for c in listed] == ["新对话", "劳动法咨询"]


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
    """SSE 协议：delta 事件增量到达，done 收尾，完整回答已持久化。"""
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
    deltas = [e["content"] for e in events if e["type"] == "delta"]
    assert "".join(deltas) == "依据知识库：试用期最长不超过六个月。"

    # 流结束后回答必须已持久化
    messages = client.get(f"/api/conversations/{conversation_id}/messages").json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "依据知识库：试用期最长不超过六个月。"


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
