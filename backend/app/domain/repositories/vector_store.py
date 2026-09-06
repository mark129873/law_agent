"""VectorStore 抽象接口。

为什么接口放在 domain 层：向量检索是 RAG 业务的领域契约，
Chroma/Milvus 只是其基础设施实现；业务层（RAG Service、Agent）
永远只依赖此接口（依赖倒置）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities.chunk import DocumentChunk, RetrievedChunk


class VectorStore(ABC):
    """向量数据库契约。

    Embedding 由调用方生成后传入：向量库实现与 embedding 模型解耦，
    未来更换 embedding 服务不需要改动任何向量库实现。
    """

    @abstractmethod
    async def initialize(self) -> None:
        """建立连接/准备存储，要求可重复调用。"""

    @abstractmethod
    async def close(self) -> None:
        """释放资源。"""

    @abstractmethod
    async def add_chunks(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> list[str]:
        """写入 chunk 及其对应向量，返回生成的 chunk id 列表。

        为什么 chunks 与 embeddings 同位传入：一一对应关系由调用方保证，
        接口不引入"批量中途失败"的歧义状态。
        """

    @abstractmethod
    async def search(self, query_embedding: list[float], top_k: int = 4) -> list[RetrievedChunk]:
        """按向量相似度检索最相关的 chunk，score 越大越相关。"""

    @abstractmethod
    async def delete_by_document(self, document_id: str) -> int:
        """删除某文档的全部 chunk，返回删除数量。"""
