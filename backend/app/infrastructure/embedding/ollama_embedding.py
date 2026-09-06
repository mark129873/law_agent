"""Ollama Embedding 服务实现。

为什么使用 /api/embed 而不是旧的 /api/embeddings：新接口支持批量输入，
一次请求完成整篇文档的向量化，避免逐 chunk 请求带来的延迟放大；
要求 Ollama 服务以 --embeddings 启动且已拉取对应模型。
"""

from __future__ import annotations

import logging

import httpx

from app.domain.services.embedding import EmbeddingService

logger = logging.getLogger("app.embedding.ollama")


class OllamaEmbeddingService(EmbeddingService):
    """基于 Ollama /api/embed 的向量生成实现。"""

    def __init__(self, base_url: str, model: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        # transport 仅供测试注入 MockTransport 使用，生产路径保持为 None
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
            extra={"service": "embedding", "model": self._model, "batch_size": len(texts)},
        )
        async with httpx.AsyncClient(timeout=120, transport=self._transport) as client:
            response = await client.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": texts},
            )
            response.raise_for_status()
            embeddings = response.json()["embeddings"]
        # 长度与输入不一致说明服务行为异常，宁可失败也不能错位入库
        if len(embeddings) != len(texts):
            raise ValueError(
                f"Embedding 返回数量不匹配：期望 {len(texts)}，实际 {len(embeddings)}"
            )
        logger.info("Embedding completed", extra={"service": "embedding", "model": self._model})
        return embeddings
