"""Ollama 本地模型 Provider。

为什么每个请求新建 AsyncClient：Ollama 是本地服务、连接开销极低，
而共享连接需要处理生命周期与并发清理；当前规模下按请求建连
是可靠性与复杂度的最佳平衡点。
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from app.domain.entities.llm import ChatMessage, LlmParams
from app.domain.repositories.llm_provider import LLMProvider

logger = logging.getLogger("app.llm.ollama")


def _to_api_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
    """领域消息转 Ollama 协议消息（角色取值恰好一致，直接使用枚举值）。"""
    return [{"role": message.role.value, "content": message.content} for message in messages]


class OllamaProvider(LLMProvider):
    """基于 Ollama /api/chat 的 Provider 实现。"""

    def __init__(
        self,
        base_url: str,
        model: str,
        enable_thinking: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        # 思考模式开关（由配置注入）：qwen3.5 等推理模型默认会先思考再回答，
        # 关闭后 Ollama 请求携带顶层字段 think:false，显著降低首字延迟
        self._enable_thinking = enable_thinking
        # transport 仅供测试注入 MockTransport 使用，生产路径保持为 None
        self._transport = transport

    @property
    def model_name(self) -> str:
        return self._model

    def _payload(self, messages: list[ChatMessage], params: LlmParams, stream: bool) -> dict:
        """构造 /api/chat 请求体：think 为顶层字段（Ollama 协议约定）。"""
        return {
            "model": self._model,
            "messages": _to_api_messages(messages),
            "stream": stream,
            "think": self._enable_thinking,
            "options": {"temperature": params.temperature},
        }

    async def chat(self, messages: list[ChatMessage], params: LlmParams | None = None) -> str:
        params = params or LlmParams()
        payload = self._payload(messages, params, stream=False)
        logger.info(
            "Ollama chat requested",
            extra={"service": "llm", "model": self._model, "message_count": len(messages)},
        )
        async with httpx.AsyncClient(timeout=300, transport=self._transport) as client:
            response = await client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            content = response.json()["message"]["content"]
        logger.info("Ollama chat completed", extra={"service": "llm", "model": self._model})
        return content

    async def stream(self, messages: list[ChatMessage], params: LlmParams | None = None) -> AsyncIterator[str]:
        params = params or LlmParams()
        payload = self._payload(messages, params, stream=True)
        logger.info(
            "Ollama stream requested",
            extra={"service": "llm", "model": self._model, "message_count": len(messages)},
        )
        # Ollama 流式返回为逐行 JSON（NDJSON），按行解析出增量 content
        async with httpx.AsyncClient(timeout=300, transport=self._transport) as client:
            async with client.stream("POST", f"{self._base_url}/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    content = event.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if event.get("done"):
                        break
        logger.info("Ollama stream completed", extra={"service": "llm", "model": self._model})
