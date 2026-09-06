"""GLM API Provider（OpenAI 兼容协议）。

为什么流式解析要容忍空行与 "data: [DONE]"：SSE 协议以空行分帧，
智谱兼容端点以 "data: [DONE]" 结束流；解析器必须跳过空帧并识别终止标记，
否则会把控制帧当内容透传给前端。
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from app.domain.entities.llm import ChatMessage, LlmParams
from app.domain.repositories.llm_provider import LLMProvider

logger = logging.getLogger("app.llm.glm")


def _to_api_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
    return [{"role": message.role.value, "content": message.content} for message in messages]


class GLMProvider(LLMProvider):
    """基于智谱 GLM OpenAI 兼容端点的 Provider 实现。"""

    def __init__(self, base_url: str, api_key: str, model: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        # transport 仅供测试注入 MockTransport 使用，生产路径保持为 None
        self._transport = transport
        # 密钥只保存在实例内存中，来自环境变量注入（见 Settings）
        self._api_key = api_key
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def chat(self, messages: list[ChatMessage], params: LlmParams | None = None) -> str:
        params = params or LlmParams()
        payload = {
            "model": self._model,
            "messages": _to_api_messages(messages),
            "stream": False,
            "temperature": params.temperature,
        }
        # 日志只记录模型名与消息数，禁止出现密钥
        logger.info(
            "GLM chat requested",
            extra={"service": "llm", "model": self._model, "message_count": len(messages)},
        )
        async with httpx.AsyncClient(timeout=120, transport=self._transport) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions", json=payload, headers=self._headers()
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        logger.info("GLM chat completed", extra={"service": "llm", "model": self._model})
        return content

    async def stream(self, messages: list[ChatMessage], params: LlmParams | None = None) -> AsyncIterator[str]:
        params = params or LlmParams()
        payload = {
            "model": self._model,
            "messages": _to_api_messages(messages),
            "stream": True,
            "temperature": params.temperature,
        }
        logger.info(
            "GLM stream requested",
            extra={"service": "llm", "model": self._model, "message_count": len(messages)},
        )
        async with httpx.AsyncClient(timeout=120, transport=self._transport) as client:
            async with client.stream(
                "POST", f"{self._base_url}/chat/completions", json=payload, headers=self._headers()
            ) as response:
                response.raise_for_status()
                # SSE 帧："data: {json}\n\n"，终止帧为 "data: [DONE]"
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
        logger.info("GLM stream completed", extra={"service": "llm", "model": self._model})
