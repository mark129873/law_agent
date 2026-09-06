"""Milvus 向量数据库骨架（扩展预留）。

为什么第一版只提供骨架：BE-008 的目标是让架构与配置可以表达
Chroma/Milvus 双 Provider，且核心 RAG 代码不存在 Chroma 强耦合；
Milvus 的完整实现留待后续版本。骨架履行 VectorStore 的全部接口签名，
使未来落地时业务层与装配结构零修改。
"""

from __future__ import annotations

from app.domain.entities.chunk import DocumentChunk, RetrievedChunk
from app.domain.repositories.vector_store import VectorStore


class MilvusVectorStore(VectorStore):
    """Milvus 实现骨架：接口已对齐，实现待后续版本提供。

    为什么调用即报错而不是返回空结果：静默的空结果会让 RAG 检索
    表现得"正常但永远查不到东西"，属于最难排查的故障；
    明确异常可以把"配了未实现的 Provider"在最早时刻暴露。
    """

    def __init__(self, uri: str) -> None:
        # uri 来自配置 MILVUS_URI，保留在实例上供未来实现直接使用
        self._uri = uri

    async def initialize(self) -> None:
        raise NotImplementedError("Milvus Provider 尚未实现（BE-008 仅预留架构）；当前可用：chroma")

    async def close(self) -> None:
        raise NotImplementedError("Milvus Provider 尚未实现（BE-008 仅预留架构）；当前可用：chroma")

    async def add_chunks(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> list[str]:
        raise NotImplementedError("Milvus Provider 尚未实现（BE-008 仅预留架构）；当前可用：chroma")

    async def search(self, query_embedding: list[float], top_k: int = 4) -> list[RetrievedChunk]:
        raise NotImplementedError("Milvus Provider 尚未实现（BE-008 仅预留架构）；当前可用：chroma")

    async def delete_by_document(self, document_id: str) -> int:
        raise NotImplementedError("Milvus Provider 尚未实现（BE-008 仅预留架构）；当前可用：chroma")
