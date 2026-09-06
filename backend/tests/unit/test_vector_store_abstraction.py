"""VectorStore 抽象接口测试。

为什么用内存 Fake：BE-006 的验收标准是"RAG 业务代码只依赖
VectorStore 抽象接口，不直接调用 Chroma API"。用与 Chroma 无关的
Fake 跑通检索业务流程即可证明这一点；BE-007 的真实 Chroma 行为
由其专属测试覆盖。
"""

import math

import pytest

from app.domain.entities.chunk import DocumentChunk, RetrievedChunk
from app.domain.repositories.vector_store import VectorStore


class InMemoryVectorStore(VectorStore):
    """内存 Fake：用余弦相似度实现检索契约。"""

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

    async def search(self, query_embedding: list[float], top_k: int = 4) -> list[RetrievedChunk]:
        def cosine(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
            return dot / norm if norm else 0.0

        scored = [
            RetrievedChunk(chunk=chunk, score=cosine(query_embedding, embedding))
            for chunk, embedding in self._chunks.values()
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    async def delete_by_document(self, document_id: str) -> int:
        doomed = [cid for cid, (chunk, _) in self._chunks.items() if chunk.document_id == document_id]
        for cid in doomed:
            del self._chunks[cid]
        return len(doomed)


async def run_retrieval_flow(store: VectorStore, query: list[float]) -> list[RetrievedChunk]:
    """典型 RAG 检索流程：写入 -> 检索。

    为什么写成普通函数：模拟未来的 RAG Service ——
    参数类型只有 VectorStore 抽象，未出现任何具体实现。
    """
    chunks = [
        DocumentChunk(document_id="doc-1", content="劳动合同违约金条款", chunk_index=0),
        DocumentChunk(document_id="doc-1", content="劳动报酬支付规定", chunk_index=1),
        DocumentChunk(document_id="doc-2", content="民法典合同编总则", chunk_index=0),
    ]
    embeddings = [
        [1.0, 0.0, 0.0],
        [0.9, 0.1, 0.0],
        [0.0, 1.0, 0.0],
    ]
    await store.add_chunks(chunks, embeddings)
    return await store.search(query, top_k=2)


@pytest.mark.asyncio
async def test_rag_flow_runs_against_abstraction() -> None:
    """检索流程在内存 Fake 上完整跑通，证明其不依赖具体向量库。"""
    store = InMemoryVectorStore()
    results = await run_retrieval_flow(store, query=[1.0, 0.05, 0.0])
    # 与查询最相关的应是 doc-1 的两个 chunk，且得分有序递减
    assert len(results) == 2
    assert all(r.chunk.document_id == "doc-1" for r in results)
    assert results[0].score >= results[1].score


@pytest.mark.asyncio
async def test_delete_by_document_scoped() -> None:
    """删除按文档隔离：doc-1 被删后 doc-2 的 chunk 仍可检索。"""
    store = InMemoryVectorStore()
    chunks = [
        DocumentChunk(document_id="doc-1", content="甲", chunk_index=0),
        DocumentChunk(document_id="doc-2", content="乙", chunk_index=0),
    ]
    await store.add_chunks(chunks, [[1.0, 0.0], [0.0, 1.0]])

    deleted = await store.delete_by_document("doc-1")
    assert deleted == 1
    remaining = await store.search([1.0, 0.0], top_k=10)
    assert [r.chunk.document_id for r in remaining] == ["doc-2"]


@pytest.mark.asyncio
async def test_add_chunks_rejects_mismatched_embeddings() -> None:
    """chunk 与 embedding 数量不一致时应立即失败，防止静默写坏数据。"""
    store = InMemoryVectorStore()
    with pytest.raises(AssertionError):
        await store.add_chunks([DocumentChunk(document_id="d", content="x")], [])
