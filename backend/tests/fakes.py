"""测试共享的领域端口内存 Fake 实现。

为什么集中在这里：多个单元/集成测试需要"实现 VectorStore 契约、
无外部依赖、行为确定"的向量库替身（与生产 Milvus 实现互换验证
同一契约）。本文件属于测试基础设施，不属于被测代码。

混合检索语义的确定性近似（与 Milvus 生产行为对齐的部分）：
- 稠密通道：余弦相似度，min_score 以 ">=" 过滤（服务端 range 语义
  的近似——真实 Milvus 的 radius 是严格大于，测试阈值取值避开了
  边界差异）；
- 词面通道：查询文本（按空白切分）为 chunk 内容的子串即命中；
  真实中文分词与 BM25 打分行为由真实 Milvus 集成测试覆盖；
- 融合：RRF（k=60，与 Milvus RRFRanker 同参数），多路命中叠加。
"""

from __future__ import annotations

import math

from app.domain.entities.chunk import DocumentChunk, RetrievedChunk
from app.domain.repositories.vector_store import VectorStore

_RRF_K = 60


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class InMemoryVectorStore(VectorStore):
    """内存 Fake：确定性实现混合检索契约。"""

    def __init__(self) -> None:
        self._chunks: dict[str, tuple[DocumentChunk, list[float]]] = {}
        self._counter = 0

    async def initialize(self) -> None: ...
    async def close(self) -> None: ...

    async def add_chunks(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> list[str]:
        assert len(chunks) == len(embeddings), "chunk 与 embedding 必须一一对应"
        ids: list[str] = []
        for chunk, embedding in zip(chunks, embeddings):
            self._counter += 1
            chunk.chunk_id = chunk.chunk_id or f"chunk-{self._counter}"
            self._chunks[chunk.chunk_id] = (chunk, embedding)
            ids.append(chunk.chunk_id)
        return ids

    async def hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        top_k: int = 4,
        min_score: float = 0.0,
    ) -> list[RetrievedChunk]:
        # 稠密通道：余弦相似度 + min_score 过滤（融合之前，语义同 Milvus）
        dense: dict[str, float] = {}
        for chunk_id, (chunk, embedding) in self._chunks.items():
            score = _cosine(query_embedding, embedding)
            if score >= min_score:
                dense[chunk_id] = score
        # 词面通道：查询词为内容的子串即命中
        tokens = [t for t in query_text.split() if t]
        keyword = [
            chunk_id
            for chunk_id, (chunk, _) in self._chunks.items()
            if any(token in chunk.content for token in tokens)
        ]
        # RRF 融合（只看排名，与生产 RRFRanker 同参数）
        scores: dict[str, float] = {}
        for rank, chunk_id in enumerate(sorted(dense, key=dense.get, reverse=True), start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank)
        for rank, chunk_id in enumerate(keyword, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[: max(1, top_k)]
        return [
            RetrievedChunk(chunk=self._chunks[chunk_id][0], score=score)
            for chunk_id, score in ranked
        ]

    async def delete_by_document(self, document_id: str) -> int:
        doomed = [cid for cid, (chunk, _) in self._chunks.items() if chunk.document_id == document_id]
        for cid in doomed:
            del self._chunks[cid]
        return len(doomed)
