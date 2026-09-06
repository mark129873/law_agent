"""Embedding 服务抽象。

为什么抽象放在 domain 层：RAG 检索质量取决于"同一种 embedding 模型
处理入库与查询"，这一约束属于领域规则；至于向量由 Ollama 还是
其他服务生成，属于基础设施细节。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingService(ABC):
    """向量生成服务契约。"""

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量生成文档向量，顺序与输入一一对应。"""

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """为检索查询生成向量。"""
