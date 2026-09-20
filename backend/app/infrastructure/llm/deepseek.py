"""DeepSeek API Provider（OpenAI 兼容 Chat Completions 协议）。

DeepSeek 的非思考模式通过 ``thinking.type=disabled`` 显式开启，避免
服务端默认进入思考流程。该类是 Infrastructure 层的适配器，只实现
Domain 的 ``LLMProvider`` 端口，装配工作仍由 containers.py 统一完成。
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from app.domain.entities.llm import ChatMessage, LlmParams
from app.domain.repositories.llm_provider import LLMProvider

logger = logging.getLogger("app.llm.deepseek")


def _to_api_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
    """把领域消息转换为 OpenAI 兼容的消息结构。"""
    return [{"role": message.role.value, "content": message.content} for message in messages]


class DeepSeekProvider(LLMProvider):
    """DeepSeek Chat Completions 适配器，固定关闭思考模式。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        # 仅供协议级测试注入 MockTransport，生产环境不改变 HTTP 客户端行为。
        self._transport = transport

    @property
    def model_name(self) -> str:
        return self._model

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, messages: list[ChatMessage], params: LlmParams, stream: bool) -> dict:
        """构造请求体，并显式关闭 DeepSeek thinking。"""
        return {
            "model": self._model,
            "messages": _to_api_messages(messages),
            "stream": stream,
            "temperature": params.temperature,
            "thinking": {"type": "disabled"},
        }

    async def chat(self, messages: list[ChatMessage], params: LlmParams | None = None) -> str:
        params = params or LlmParams()
        payload = self._payload(messages, params, stream=False)
        logger.info(
            "DeepSeek chat requested",
            extra={"service": "llm", "model": self._model, "message_count": len(messages)},
        )
        async with httpx.AsyncClient(timeout=300, transport=self._transport) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions", json=payload, headers=self._headers()
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        logger.info("DeepSeek chat completed", extra={"service": "llm", "model": self._model})
        return content

    async def stream(self, messages: list[ChatMessage], params: LlmParams | None = None) -> AsyncIterator[str]:
        params = params or LlmParams()
        payload = self._payload(messages, params, stream=True)
        logger.info(
            "DeepSeek stream requested",
            extra={"service": "llm", "model": self._model, "message_count": len(messages)},
        )
        async with httpx.AsyncClient(timeout=300, transport=self._transport) as client:
            async with client.stream(
                "POST", f"{self._base_url}/chat/completions", json=payload, headers=self._headers()
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    delta = event["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
        logger.info("DeepSeek stream completed", extra={"service": "llm", "model": self._model})
