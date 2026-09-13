"""混合检索服务：适配领域端口（BE-033，设计 §29，ADR-0003）。

为什么不直连 pymilvus SDK（设计约束 25）：Dense + BM25 + RRF 融合
已由 MilvusVectorStore 在服务端一次 hybrid_search 完成（BE-029），
设计 §29 接口中的 dense_top_k/bm25_top_k/rrf_k 属服务端融合细节
（RRFRanker k=60 已固化），端口契约只暴露融合后 top_k 与稠密通道
min_score，语义等价。
"""

from __future__ import annotations

import logging

from app.domain.entities.chunk import RetrievedChunk
from app.domain.repositories.vector_store import VectorStore
from app.domain.services.embedding import EmbeddingService

logger = logging.getLogger("app.agent.services.milvus")


class MilvusService:
    """知识库混合检索服务：查询向量化 + 服务端融合检索。"""

    def __init__(self, embedding: EmbeddingService, vector_store: VectorStore) -> None:
        self._embedding = embedding
        self._vector_store = vector_store

    async def hybrid_search(
        self,
        query: str,
        *,
        top_k: int = 20,
        min_score: float = 0.0,
    ) -> list[RetrievedChunk]:
        """单查询混合检索（融合后 top_k，score 越大越相关）。

        min_score 语义与端口一致：只过滤稠密通道弱命中（融合之前）。
        多 Query 并发由调用方（hybrid_retriever_node）编排，
        本服务保持单查询契约。
        """
        query_vector = await self._embedding.embed_query(query)
        results = await self._vector_store.hybrid_search(
            query, query_vector, top_k=top_k, min_score=min_score
        )
        logger.info(
            "Agent hybrid search completed",
            extra={
                "service": "agent",
                "query_length": len(query),
                "hit_count": len(results),
                "top_score": results[0].score if results else 0.0,
            },
        )
        return results
