"""Chroma 向量数据库实现。

为什么所有调用都包在 asyncio.to_thread 里：chromadb 客户端是同步阻塞实现，
直接在事件循环中调用会阻塞 FastAPI 的整个事件循环；
Architecture.md 第 10 节要求全链路异步、不允许阻塞事件循环。
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection

from app.domain.entities.chunk import DocumentChunk, RetrievedChunk
from app.domain.repositories.vector_store import VectorStore

# 法律知识库固定集合名：单集合 + metadata 过滤即可满足当前规模，
# 多集合带来的复杂度在当前阶段没有必要。
_COLLECTION_NAME = "law_chunks"


def _new_chunk_id() -> str:
    """生成 chunk 主键，与 SQLite 仓库同样使用 uuid 保证与存储解耦。"""
    return uuid.uuid4().hex


class ChromaVectorStore(VectorStore):
    """基于 chromadb PersistentClient 的 VectorStore 抽象实现。"""

    def __init__(self, persist_dir: str) -> None:
        self._persist_dir = Path(persist_dir)
        self._client: chromadb.ClientAPI | None = None
        self._collection: Collection | None = None

    async def initialize(self) -> None:
        def _init() -> Collection:
            # PersistentClient 数据落盘，重启后向量不丢失
            client = chromadb.PersistentClient(path=str(self._persist_dir))
            # cosine 空间下 score = 1 - distance，天然满足"越大越相关"的接口约定
            return client.get_or_create_collection(
                name=_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )

        await asyncio.to_thread(
            lambda: (self._persist_dir).mkdir(parents=True, exist_ok=True)
        )
        self._collection = await asyncio.to_thread(_init)

    async def close(self) -> None:
        # chromadb 无显式连接句柄，落盘由内部管理；置空引用即可
        self._collection = None
        self._client = None

    def _require_collection(self) -> Collection:
        assert self._collection is not None, "必须先调用 initialize()"
        return self._collection

    async def add_chunks(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> list[str]:
        assert len(chunks) == len(embeddings), "chunk 与 embedding 必须一一对应"

        ids: list[str] = []
        for chunk in chunks:
            chunk.chunk_id = chunk.chunk_id or _new_chunk_id()
            ids.append(chunk.chunk_id)

        def _add() -> None:
            self._require_collection().add(
                ids=ids,
                embeddings=embeddings,
                documents=[chunk.content for chunk in chunks],
                # chroma metadata 只接受标量值，document_id 必须入库以支持按文档删除
                metadatas=[
                    {
                        "document_id": chunk.document_id,
                        "chunk_index": chunk.chunk_index,
                        **{k: v for k, v in chunk.metadata.items() if isinstance(v, (str, int, float, bool))},
                    }
                    for chunk in chunks
                ],
            )

        await asyncio.to_thread(_add)
        return ids

    async def search(self, query_embedding: list[float], top_k: int = 4) -> list[RetrievedChunk]:
        def _query() -> dict:
            result = self._require_collection().query(
                query_embeddings=[query_embedding],
                n_results=max(1, top_k),
                include=["documents", "metadatas", "distances"],
            )
            return result

        result = await asyncio.to_thread(_query)
        hits: list[RetrievedChunk] = []
        for chunk_id, document, metadata, distance in zip(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            chunk = DocumentChunk(
                chunk_id=chunk_id,
                document_id=str(metadata.get("document_id", "")),
                content=document,
                chunk_index=int(metadata.get("chunk_index", 0)),
                # 只还原来源类标量字段，内部键不透传给业务层
                metadata={
                    k: v
                    for k, v in metadata.items()
                    if k not in ("document_id", "chunk_index") and isinstance(v, str)
                },
            )
            hits.append(RetrievedChunk(chunk=chunk, score=1.0 - float(distance)))
        return hits

    async def delete_by_document(self, document_id: str) -> int:
        def _ids_to_delete() -> list[str]:
            # count() 不支持 where 过滤，先用 get 取出命中的 chunk id
            found = self._require_collection().get(where={"document_id": document_id}, include=[])
            return list(found["ids"])

        def _delete() -> None:
            self._require_collection().delete(where={"document_id": document_id})

        doomed_ids = await asyncio.to_thread(_ids_to_delete)
        if doomed_ids:
            await asyncio.to_thread(_delete)
        return len(doomed_ids)
