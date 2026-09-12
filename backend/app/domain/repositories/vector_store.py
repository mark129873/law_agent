"""VectorStore 抽象接口（BE-029 起为混合检索契约）。

为什么接口放在 domain 层：知识库检索是 RAG 业务的领域契约，
Milvus 只是其基础设施实现；业务层（RAG Service、Agent）
永远只依赖此接口（依赖倒置）。

为什么检索方法是 hybrid_search 而非纯向量 search：
向量库（Milvus）同时持有稠密向量与稀疏 BM25 向量，两路检索
与 RRF 融合在服务端一次完成——接口以"知识库混合检索"这一
领域能力命名，调用方不感知融合发生在哪个通道、用什么算法。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities.chunk import DocumentChunk, RetrievedChunk


class VectorStore(ABC):
    """向量数据库契约（混合检索）。

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
        """写入 chunk 及其稠密向量，返回生成的 chunk id 列表。

        为什么 chunks 与 embeddings 同位传入：一一对应关系由调用方保证，
        接口不引入"批量中途失败"的歧义状态。
        稀疏 BM25 表示不需要调用方提供：由存储实现按 chunk 文本自行生成。
        """

    @abstractmethod
    async def hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        top_k: int = 4,
        min_score: float = 0.0,
    ) -> list[RetrievedChunk]:
        """混合检索最相关的 chunk，score 越大越相关。

        query_text 供词面检索通道（BM25）使用，query_embedding 供
        语义检索通道使用；两路结果由实现方融合后统一返回。
        min_score 为稠密通道的相似度下限（默认 0.0 不过滤），
        弱命中在融合之前被剔除。
        """

    @abstractmethod
    async def delete_by_document(self, document_id: str) -> int:
        """删除某文档的全部 chunk，返回删除数量。"""
