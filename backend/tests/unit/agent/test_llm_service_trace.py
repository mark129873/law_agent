"""LLMService generation 采集单元测试（BE-043，ADR-0010）。

用假 Provider + 假 span 锁定三条调用路径（invoke/structured_invoke/
stream）的 generation 记录契约与无 span 时的零干扰行为。
"""

import asyncio

from pydantic import BaseModel

from app.agent.services.llm_service import LLMService
from app.agent.trace_context import trace_span_var
from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole
from app.domain.repositories.llm_provider import LLMProvider


class RecordingSpan:
    """假节点 span：记录 generation 调用。"""

    def __init__(self) -> None:
        self.generations: list[dict] = []
        self.ended = False

    def record_generation(self, **kwargs) -> None:
        self.generations.append(kwargs)

    def end(self, *, duration_ms=None, error=None) -> None:
        self.ended = True


class ScriptedProvider(LLMProvider):
    """脚本化 Provider：按脚本返回 chat 输出/流式增量/异常。"""

    def __init__(self, chat_outputs: list[str] | None = None, stream_chunks: list[str] | None = None,
                 chat_error: Exception | None = None, stream_error: Exception | None = None) -> None:
        self._chat_outputs = chat_outputs or []
        self._stream_chunks = stream_chunks or []
        self._chat_error = chat_error
        self._stream_error = stream_error

    @property
    def model_name(self) -> str:
        return "fake-model"

    async def chat(self, messages: list[ChatMessage], params=None) -> str:
        if self._chat_error is not None:
            raise self._chat_error
        return self._chat_outputs.pop(0) if self._chat_outputs else "{}"

    async def stream(self, messages: list[ChatMessage], params=None):
        for chunk in self._stream_chunks:
            yield chunk
        if self._stream_error is not None:
            raise self._stream_error


class _Schema(BaseModel):
    intent: str = "legal_question"


def _messages() -> list[ChatMessage]:
    return [ChatMessage(role=MessageRole.USER, content="问题")]


def _run_with_span(coroutine_factory):
    """在携带假 span 的上下文中执行。"""
    async def _run():
        span = RecordingSpan()
        token = trace_span_var.set(span)
        try:
            result = await coroutine_factory()
        finally:
            trace_span_var.reset(token)
        return span, result
    return asyncio.run(_run())


def test_invoke_records_generation_with_output_and_duration():
    provider = ScriptedProvider(chat_outputs=["回答全文"])
    service = LLMService(provider)
    span, answer = _run_with_span(lambda: service.invoke(_messages()))
    assert answer == "回答全文"
    assert len(span.generations) == 1
    gen = span.generations[0]
    assert gen["model"] == "fake-model"
    assert gen["output"] == "回答全文"
    assert gen["messages"] == [{"role": "user", "content": "问题"}]
    assert gen["duration_ms"] is not None
    assert gen["error"] is None


def test_invoke_error_records_generation_and_reraises():
    provider = ScriptedProvider(chat_error=RuntimeError("连接失败"))
    service = LLMService(provider)

    async def _call():
        try:
            await service.invoke(_messages())
            raise AssertionError("应当上抛")
        except RuntimeError as error:
            assert str(error) == "连接失败"

    span, _ = _run_with_span(_call)
    assert len(span.generations) == 1
    assert span.generations[0]["error"] == "连接失败"


def test_stream_records_generation_with_aggregated_output():
    provider = ScriptedProvider(stream_chunks=["你好", "，", "世界"])
    service = LLMService(provider)

    async def _call():
        chunks = []
        async for chunk in service.stream(_messages()):
            chunks.append(chunk)
        return chunks

    span, chunks = _run_with_span(_call)
    assert chunks == ["你好", "，", "世界"]
    assert len(span.generations) == 1
    assert span.generations[0]["output"] == "你好，世界"
    assert span.generations[0]["metadata"] == {"mode": "stream"}


def test_stream_error_records_partial_output_and_reraises():
    provider = ScriptedProvider(stream_chunks=["半截"], stream_error=RuntimeError("中断"))
    service = LLMService(provider)

    async def _call():
        chunks = []
        try:
            async for chunk in service.stream(_messages()):
                chunks.append(chunk)
        except RuntimeError:
            pass
        return chunks

    span, chunks = _run_with_span(_call)
    assert chunks == ["半截"]
    assert span.generations[0]["output"] == "半截"
    assert span.generations[0]["error"] == "中断"


def test_structured_invoke_records_each_attempt_with_parsed_flag():
    provider = ScriptedProvider(chat_outputs=["不是 JSON 的输出", '{"intent": "general_question"}'])
    service = LLMService(provider)
    span, parsed = _run_with_span(
        lambda: service.structured_invoke(_messages(), _Schema, default=_Schema())
    )
    assert parsed.intent == "general_question"  # 第二次尝试解析成功
    assert len(span.generations) == 2
    assert span.generations[0]["metadata"]["attempt"] == "1"
    assert span.generations[0]["metadata"]["parsed"] == "false"
    assert span.generations[1]["metadata"]["attempt"] == "2"
    assert span.generations[1]["metadata"]["parsed"] == "true"


def test_structured_invoke_default_records_unparsable_attempts():
    provider = ScriptedProvider(chat_outputs=["垃圾输出", "还是垃圾"])
    service = LLMService(provider)
    span, parsed = _run_with_span(
        lambda: service.structured_invoke(_messages(), _Schema, default=_Schema(intent="fallback"))
    )
    assert parsed.intent == "fallback"  # 重试耗尽走安全默认
    assert len(span.generations) == 2


def test_no_span_means_no_recording_and_passthrough():
    """无 span（未启用 trace）：纯透传，不记任何内容。"""
    provider = ScriptedProvider(chat_outputs=["ok"], stream_chunks=["s"])
    service = LLMService(provider)

    async def _run():
        # 不设置 trace_span_var（默认 None）
        answer = await service.invoke(_messages())
        chunks = []
        async for chunk in service.stream(_messages()):
            chunks.append(chunk)
        return answer, chunks

    answer, chunks = asyncio.run(_run())
    assert answer == "ok" and chunks == ["s"]
