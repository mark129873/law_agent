"""KeywordIndex 抽象接口（BE-028 混合检索）。

为什么接口放在 domain 层：关键词检索是 RAG 业务的领域契约，
BM25 只是其基础设施实现；业务层（RagService、入库/删除编排）
永远只依赖此接口（依赖倒置），未来换其他关键词检索实现
（如 SQLite FTS、Elasticsearch）不需要改动任何业务代码。

与 VectorStore 端口的关系：二者是并列的两条检索通道——
向量通道管"语义相似"，关键词通道管"词面精确匹配"；
接口形状刻意保持同构（add/search/delete_by_document），
让调用方可以用同一套编排逻辑维护两路数据的一致性。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities.chunk import DocumentChunk, RetrievedChunk


class KeywordIndex(ABC):
    """关键词检索索引契约。

    为什么 embedding 不在这里出现：关键词索引按词面匹配，
    不需要向量化，接口因此比 VectorStore 更简单（add_chunks
    不要求调用方先算 embedding）。
    """

    @abstractmethod
    async def initialize(self) -> None:
        """加载/重建索引，要求可重复调用（幂等）。"""

    @abstractmethod
    async def close(self) -> None:
        """释放资源。"""

    @abstractmethod
    async def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        """把 chunk 追加进关键词索引。

        为什么与 VectorStore.add_chunks 同构：入库编排服务
        （KnowledgeIngestionService）负责双写，同构接口让
        "向量库写入成功后紧跟关键词索引写入"的顺序一目了然。
        """

    @abstractmethod
    async def search(self, query: str, top_k: int = 4) -> list[RetrievedChunk]:
        """按关键词词面匹配检索最相关的 chunk，score 越大越相关。

        与 VectorStore.search 的关键差异：入参是原始查询文本
        而非查询向量——分词是索引实现自己的职责，调用方不感知。
        """

    @abstractmethod
    async def delete_by_document(self, document_id: str) -> int:
        """删除某文档的全部 chunk，返回删除数量。"""
