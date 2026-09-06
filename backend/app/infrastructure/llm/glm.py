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
    """领域消息 → OpenAI 兼容协议消息（与 Ollama 共用角色取值，无需映射表）。"""
    return [{"role": message.role.value, "content": message.content} for message in messages]


class GLMProvider(LLMProvider):
    """基于智谱 GLM OpenAI 兼容端点的 Provider 实现。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        enable_thinking: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # transport 仅供测试注入 MockTransport 使用，生产路径保持为 None
        self._transport = transport
        # 密钥只保存在实例内存中，来自环境变量注入（见 Settings）
        self._api_key = api_key
        self._model = model
        # 思考模式开关（由配置注入）：glm-4.5 系列支持 thinking.type 参数，
        # 关闭后响应不再生成思考内容，显著降低首字延迟
        self._enable_thinking = enable_thinking

    @property
    def model_name(self) -> str:
        return self._model

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, messages: list[ChatMessage], params: LlmParams, stream: bool) -> dict:
        """构造 chat/completions 请求体：thinking.type 为智谱扩展字段。"""
        return {
            "model": self._model,
            "messages": _to_api_messages(messages),
            "stream": stream,
            "temperature": params.temperature,
            "thinking": {"type": "enabled" if self._enable_thinking else "disabled"},
        }

    async def chat(self, messages: list[ChatMessage], params: LlmParams | None = None) -> str:
        params = params or LlmParams()
        payload = self._payload(messages, params, stream=False)
        # 日志只记录模型名与消息数，禁止出现密钥
        logger.info(
            "GLM chat requested",
            extra={"service": "llm", "model": self._model, "message_count": len(messages)},
        )
        async with httpx.AsyncClient(timeout=300, transport=self._transport) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions", json=payload, headers=self._headers()
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        logger.info("GLM chat completed", extra={"service": "llm", "model": self._model})
        return content

    async def stream(self, messages: list[ChatMessage], params: LlmParams | None = None) -> AsyncIterator[str]:
        params = params or LlmParams()
        payload = self._payload(messages, params, stream=True)
        logger.info(
            "GLM stream requested",
            extra={"service": "llm", "model": self._model, "message_count": len(messages)},
        )
        async with httpx.AsyncClient(timeout=300, transport=self._transport) as client:
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
