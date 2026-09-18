"""Ollama、GLM 与 DeepSeek Provider 测试。

为什么用 httpx.MockTransport：云端模型真实调用需要 API Key，
Ollama 真实调用则作为独立 smoke 验证单独运行；协议级测试证明各个
Provider 的请求构造、响应解析与流式拆包逻辑正确，可随时替换真实服务。
"""

import json

import httpx
import pytest

from app.domain.entities.llm import ChatMessage, LlmParams
from app.domain.entities.message import MessageRole
from app.infrastructure.llm.deepseek import DeepSeekProvider
from app.infrastructure.llm.glm import GLMProvider
from app.infrastructure.llm.ollama import OllamaProvider


@pytest.mark.asyncio
async def test_ollama_chat_parses_content() -> None:
    """Ollama 同步问答应解析 message.content 并携带模型名与 stream:false。"""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["stream"] is False
        assert payload["messages"][0]["role"] == "user"
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "回答内容"}})

    provider = OllamaProvider("http://mock", "test-model", transport=httpx.MockTransport(handler))
    answer = await provider.chat([ChatMessage(role=MessageRole.USER, content="问题")])
    assert answer == "回答内容"


@pytest.mark.asyncio
async def test_ollama_stream_parses_ndjson() -> None:
    """Ollama 流式返回 NDJSON，应逐行解析出增量 content 并在 done 后停止。"""
    lines = "\n".join(
        [
            json.dumps({"message": {"content": "第一段"}, "done": False}),
            "",  # 空行应被跳过
            json.dumps({"message": {"content": "第二段"}, "done": False}),
            json.dumps({"message": {"content": ""}, "done": True}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, content=lines.encode("utf-8"))

    provider = OllamaProvider("http://mock", "test-model", transport=httpx.MockTransport(handler))
    chunks = [chunk async for chunk in provider.stream([ChatMessage(role=MessageRole.USER, content="问题")])]
    assert chunks == ["第一段", "第二段"]


@pytest.mark.asyncio
async def test_glm_chat_parses_choices() -> None:
    """GLM 同步问答应携带 Bearer 密钥并解析 choices[0].message.content。"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "法律回答"}}]})

    provider = GLMProvider("http://mock", "test-key", "glm-4-flash", transport=httpx.MockTransport(handler))
    answer = await provider.chat([ChatMessage(role=MessageRole.USER, content="问题")])
    assert answer == "法律回答"


@pytest.mark.asyncio
async def test_glm_stream_parses_sse() -> None:
    """GLM 流式返回 SSE，应解析 data 帧中的 delta.content 并在 [DONE] 终止。"""
    sse = (
        'data: {"choices": [{"delta": {"content": "依据"}}]}\n\n'
        "\n"  # 空帧应被跳过
        'data: {"choices": [{"delta": {"content": "如下"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse.encode("utf-8"))

    provider = GLMProvider("http://mock", "test-key", "glm-4-flash", transport=httpx.MockTransport(handler))
    chunks = [chunk async for chunk in provider.stream([ChatMessage(role=MessageRole.USER, content="问题")])]
    assert chunks == ["依据", "如下"]


@pytest.mark.asyncio
async def test_deepseek_chat_disables_thinking() -> None:
    """DeepSeek 请求必须显式关闭 thinking，并解析 OpenAI 兼容响应。"""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert payload["model"] == "deepseek-chat"
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["stream"] is False
        return httpx.Response(200, json={"choices": [{"message": {"content": "DeepSeek 回答"}}]})

    provider = DeepSeekProvider(
        "http://mock", "test-key", "deepseek-chat", transport=httpx.MockTransport(handler)
    )
    assert await provider.chat([ChatMessage(role=MessageRole.USER, content="问题")]) == "DeepSeek 回答"


@pytest.mark.asyncio
async def test_deepseek_stream_parses_sse() -> None:
    """DeepSeek 流式响应只向领域层产出最终答案 content。"""
    sse = (
        'data: {"choices": [{"delta": {"content": "第一段"}}]}\n\n'
        'data: {"choices": [{"delta": {"reasoning_content": "不会透传"}}]}\n\n'
        'data: {"choices": [{"delta": {"content": "第二段"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["thinking"] == {"type": "disabled"}
        return httpx.Response(200, content=sse.encode("utf-8"))

    provider = DeepSeekProvider(
        "http://mock", "test-key", "deepseek-chat", transport=httpx.MockTransport(handler)
    )
    chunks = [chunk async for chunk in provider.stream([ChatMessage(role=MessageRole.USER, content="问题")])]
    assert chunks == ["第一段", "第二段"]


@pytest.mark.asyncio
async def test_llm_error_raises_for_status() -> None:
    """模型服务返回错误时应抛出异常而不是静默返回空内容。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "server busy"})

    provider = OllamaProvider("http://mock", "test-model", transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await provider.chat([ChatMessage(role=MessageRole.USER, content="问题")])


@pytest.mark.asyncio
async def test_llm_params_forwarded() -> None:
    """temperature 等参数应进入请求体。"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "ok"}})

    provider = OllamaProvider("http://mock", "test-model", transport=httpx.MockTransport(handler))
    await provider.chat([ChatMessage(role=MessageRole.USER, content="q")], LlmParams(temperature=0.3))
    assert captured["payload"]["options"]["temperature"] == 0.3


@pytest.mark.asyncio
async def test_ollama_think_switch_in_payload() -> None:
    """Ollama 请求体应携带顶层 think 开关：默认关闭，可经构造参数开启。"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "ok"}})

    # 默认（配置未开启）：think=false，避免推理模型的思考过程拉长首字延迟
    provider = OllamaProvider("http://mock", "test-model", transport=httpx.MockTransport(handler))
    [chunk async for chunk in provider.stream([ChatMessage(role=MessageRole.USER, content="q")])]
    assert captured["payload"]["think"] is False

    # 显式开启：think=true
    provider_enabled = OllamaProvider(
        "http://mock", "test-model", enable_thinking=True, transport=httpx.MockTransport(handler)
    )
    await provider_enabled.chat([ChatMessage(role=MessageRole.USER, content="q")])
    assert captured["payload"]["think"] is True


@pytest.mark.asyncio
async def test_glm_thinking_switch_in_payload() -> None:
    """GLM 请求体应携带 thinking.type：默认 disabled，可经构造参数切换为 enabled。"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = GLMProvider(
        "http://mock", "test-key", "glm-4.5-air", transport=httpx.MockTransport(handler)
    )
    await provider.chat([ChatMessage(role=MessageRole.USER, content="q")])
    assert captured["payload"]["thinking"] == {"type": "disabled"}

    provider_enabled = GLMProvider(
        "http://mock", "test-key", "glm-4.5-air", enable_thinking=True, transport=httpx.MockTransport(handler)
    )
    [chunk async for chunk in provider_enabled.stream([ChatMessage(role=MessageRole.USER, content="q")])]
    assert captured["payload"]["thinking"] == {"type": "enabled"}
