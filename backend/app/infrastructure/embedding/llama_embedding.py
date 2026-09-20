"""llama.cpp `llama serve` Embedding HTTP 适配器。

为什么单独实现：Embedding 是领域端口，具体服务只负责把批量文本转换成
`/v1/embeddings` 的向量，应用层不感知 HTTP 协议，也不绑定 Ollama。
使用 OpenAI 兼容响应的 ``data[index].embedding`` 结构，按 index 恢复顺序，
避免服务端并行处理后把向量与原文错位。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.domain.services.embedding import EmbeddingService

logger = logging.getLogger("app.embedding.llama")


class LlamaEmbeddingService(EmbeddingService):
    """调用 llama serve `/v1/embeddings` 生成批量向量。"""

    def __init__(
        self,
        base_url: str,
        model_path: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_path = model_path
        # transport 仅供协议测试注入 MockTransport，生产路径保持 None。
        self._transport = transport

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed([text])
        return vectors[0]

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        logger.info(
            "Embedding requested",
            extra={
                "service": "embedding",
                "provider": "llama",
                "model": self._model_path,
                "batch_size": len(texts),
            },
        )
        async with httpx.AsyncClient(timeout=120, transport=self._transport) as client:
            response = await client.post(
                f"{self._base_url}/v1/embeddings",
                json={"model": self._model_path, "input": texts},
            )
            response.raise_for_status()
            payload: Any = response.json()

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise ValueError("llama serve Embedding 响应缺少 data 数组")
        try:
            ordered = sorted(data, key=lambda item: int(item["index"]))
            embeddings = [item["embedding"] for item in ordered]
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("llama serve Embedding 响应格式非法") from error
        if len(embeddings) != len(texts):
            raise ValueError(
                f"Embedding 返回数量不匹配：期望 {len(texts)}，实际 {len(embeddings)}"
            )
        indexes = [int(item["index"]) for item in ordered]
        if indexes != list(range(len(texts))):
            raise ValueError("llama serve Embedding 响应 index 非法或重复")
        if any(not isinstance(vector, list) for vector in embeddings):
            raise ValueError("llama serve Embedding 响应中的 embedding 必须是数组")
        logger.info(
            "Embedding completed",
            extra={"service": "embedding", "provider": "llama", "model": self._model_path},
        )
        return embeddings
