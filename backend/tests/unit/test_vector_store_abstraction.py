"""VectorStore 抽象接口测试。

为什么用内存 Fake：BE-006 的验收标准是"RAG 业务代码只依赖
VectorStore 抽象接口，不直接调用向量库 API"。用与任何向量库无关的
Fake 跑通检索业务流程即可证明这一点；BE-029 起的真实 Milvus 混合
检索行为由 tests/integration/test_milvus_vector_store.py 覆盖。
"""

import pytest

from app.domain.entities.chunk import DocumentChunk, RetrievedChunk
from app.domain.repositories.vector_store import VectorStore
from tests.fakes import InMemoryVectorStore


async def run_retrieval_flow(store: VectorStore, query_text: str, query_vector: list[float]) -> list[RetrievedChunk]:
    """典型 RAG 混合检索流程：写入 -> hybrid_search。

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
    return await store.hybrid_search(query_text, query_vector, top_k=2)


@pytest.mark.asyncio
async def test_rag_flow_runs_against_abstraction() -> None:
    """检索流程在内存 Fake 上完整跑通，证明其不依赖具体向量库。"""
    store = InMemoryVectorStore()
    results = await run_retrieval_flow(store, query_text="违约金", query_vector=[1.0, 0.05, 0.0])
    # 与查询最相关的应是 doc-1 的两个 chunk，且得分有序递减
    assert len(results) == 2
    assert all(r.chunk.document_id == "doc-1" for r in results)
    assert results[0].score >= results[1].score


@pytest.mark.asyncio
async def test_hybrid_search_keyword_channel_hits_content() -> None:
    """词面通道：查询词命中内容时应召回对应 chunk（词面通道语义）。"""
    store = InMemoryVectorStore()
    await store.add_chunks(
        [DocumentChunk(document_id="doc-1", content="劳动合同违约金条款", chunk_index=0)],
        [[0.0, 1.0, 0.0]],  # 稠密向量与查询正交：语义通道不得命中
    )
    results = await store.hybrid_search("违约金 条款", [1.0, 0.0, 0.0], top_k=4)
    assert len(results) == 1
    assert "违约金" in results[0].chunk.content


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
    remaining = await store.hybrid_search("甲", [1.0, 0.0], top_k=10)
    assert [r.chunk.document_id for r in remaining] == ["doc-2"]


@pytest.mark.asyncio
async def test_add_chunks_rejects_mismatched_embeddings() -> None:
    """chunk 与 embedding 数量不一致时应立即失败，防止静默写坏数据。"""
    store = InMemoryVectorStore()
    with pytest.raises(AssertionError):
        await store.add_chunks([DocumentChunk(document_id="d", content="x")], [])
