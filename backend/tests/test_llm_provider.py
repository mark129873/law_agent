"""LLMProvider 抽象接口测试。

为什么用 Fake：BE-009 的验收标准是"Agent 可以通过统一 LLM 接口调用模型，
并能够独立替换具体 LLM Provider"。Fake 证明业务代码只依赖抽象；
真实 Ollama/GLM 行为由 BE-010 的专属测试覆盖。
"""

from typing import AsyncIterator

import pytest

from app.domain.entities.llm import ChatMessage, LlmParams
from app.domain.entities.message import MessageRole
from app.domain.repositories.llm_provider import LLMProvider


class FakeLLMProvider(LLMProvider):
    """内存 Fake：按词切分流式产出，模拟真实 token 流。"""

    def __init__(self, answer: str) -> None:
        self._answer = answer

    @property
    def model_name(self) -> str:
        return "fake-model"

    async def chat(self, messages: list[ChatMessage], params: LlmParams | None = None) -> str:
        return self._answer

    async def stream(self, messages: list[ChatMessage], params: LlmParams | None = None) -> AsyncIterator[str]:
        for word in self._answer.split(" "):
            yield word + " "


async def run_qa_flow(provider: LLMProvider, question: str) -> tuple[str, str]:
    """典型问答流程：同步回答 + 流式拼接。

    为什么写成普通函数：模拟未来的 ChatService ——
    参数类型只有 LLMProvider 抽象，未出现任何具体实现。
    """
    messages = [ChatMessage(role=MessageRole.USER, content=question)]
    full_answer = await provider.chat(messages)
    streamed = "".join([chunk async for chunk in provider.stream(messages)])
    return full_answer, streamed


@pytest.mark.asyncio
async def test_qa_flow_runs_against_abstraction() -> None:
    """业务流程在 Fake 上完整跑通，同步与流式结果一致且不依赖具体实现。"""
    full, streamed = await run_qa_flow(FakeLLMProvider("根据劳动合同法 第四十七条 …"), "经济补偿怎么算？")
    assert full == "根据劳动合同法 第四十七条 …"
    assert streamed.replace(" ", "") == full.replace(" ", "")


@pytest.mark.asyncio
async def test_stream_yields_incremental_chunks() -> None:
    """流式接口必须产出多个增量片段，这是前端逐字渲染的前提。"""
    provider = FakeLLMProvider("a b c d")
    chunks = [chunk async for chunk in provider.stream([])]
    assert len(chunks) == 4


@pytest.mark.asyncio
async def test_params_forwarded_to_provider() -> None:
    """调用参数应完整传入 Provider，便于实现侧控制采样行为。"""
    captured: dict = {}

    class CapturingProvider(FakeLLMProvider):
        async def chat(self, messages: list[ChatMessage], params: LlmParams | None = None) -> str:
            captured["params"] = params
            return await super().chat(messages, params)

    await CapturingProvider("ok").chat([], LlmParams(temperature=0.2, max_tokens=128))
    assert captured["params"] is not None
    assert captured["params"].temperature == 0.2
    assert captured["params"].max_tokens == 128
