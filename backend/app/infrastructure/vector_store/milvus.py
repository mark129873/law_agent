"""Milvus 向量数据库实现（BE-029 混合检索）。

技术方案：
- 单一集合同时持有稠密向量（FLOAT_VECTOR/COSINE，由调用方传入的
  embedding）与稀疏向量（SPARSE_FLOAT_VECTOR）；
- 稀疏表示由 Milvus 服务端的 BM25 Function 按 content 字段自动生成，
  content 启用 jieba 分词器——中文法条词面匹配不需要客户端分词；
- hybrid_search 一次调用同时发起稠密 + 稀疏两路 AnnSearchRequest，
  服务端 RRFRanker(k=rrf_k) 融合；每路可独立配置候选上限
  dense_top_k / bm25_top_k，融合后再截断到 top_k（融合后返回量）；
- 集合在首次 add_chunks 时按实际 embedding 维度懒建（稠密维度跟随
  embedding 模型，不写死配置）；检索在集合不存在时返回空（空知识库语义）。

一致性说明：create/search 显式使用 consistency_level="Strong"，保证
"入库即可检索"（测试依赖此语义）。为什么必须 Strong：默认 Bounded
一致性下新插入数据对检索不可见，hybrid_search 空结果会触发 Milvus
已知缺陷（issue #50969：空结果被误报为 unsupported ID type）。

并发模型：pymilvus 客户端是同步阻塞实现，所有调用经 asyncio.to_thread
包装避免阻塞 FastAPI 事件循环；用 threading.Lock 保护懒建集合的并发
创建（检索只读集合，与建集合互斥即可）。
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid

from pymilvus import AnnSearchRequest, DataType, Function, FunctionType, MilvusClient, RRFRanker

from app.domain.entities.chunk import DocumentChunk, RetrievedChunk
from app.domain.repositories.vector_store import VectorStore

logger = logging.getLogger("app.vector_store.milvus")

# 法律知识库固定集合名：单集合即可满足当前规模（与迁移前 Chroma 集合同名），
# 测试经构造参数注入独立集合名，避免污染生产数据。
_DEFAULT_COLLECTION = "law_chunks"


def _new_chunk_id() -> str:
    """生成 chunk 主键，与领域仓储同样使用 uuid 保证与存储解耦。"""
    return uuid.uuid4().hex


class MilvusVectorStore(VectorStore):
    """基于 pymilvus MilvusClient 的 VectorStore 抽象实现（混合检索）。

    构造参数均有生产默认值，测试可按需覆盖以验证参数透传。
    dense_top_k / bm25_top_k 控制每路候选预取量，rrf_k 控制融合平滑。
    """

    def __init__(
        self,
        uri: str,
        collection_name: str = _DEFAULT_COLLECTION,
        min_score: float = 0.0,
        dense_top_k: int = 30,
        bm25_top_k: int = 30,
        rrf_k: int = 60,
        token: str = "",
    ) -> None:
        self._uri = uri
        self._collection_name = collection_name
        # Milvus Cloud 使用 API Key 作为 token；本地 standalone 通常为空。
        # 只保存在内存中，禁止进入日志或其他持久化数据。
        self._token = token
        # 默认相似度下限：调用方（RagService）也可按次传入覆盖
        self._default_min_score = min_score
        # 每路候选预取量：dense/bm25 各自取 top N 后交给 RRF 融合，
        # 比只取融合后 top_k 召回率更高，代价是多取少量候选（可忽略）
        self._dense_top_k = dense_top_k
        self._bm25_top_k = bm25_top_k
        # RRF 平滑常数：论文推荐值 60，排名越靠前贡献越大
        self._rrf_k = rrf_k
        self._client: MilvusClient | None = None
        # 集合是否已确认存在（懒建标记；False 时检索直接返回空）
        self._collection_ready = False
        # 懒建集合互斥锁：并发首次写入时只有一个线程真正建集合
        self._ensure_lock = threading.Lock()

    # ---- 生命周期 ----

    async def initialize(self) -> None:
        """建立连接；集合已存在（重启场景）则加载，不存在则等首次入库懒建。"""
        def _connect() -> None:
            client_kwargs: dict[str, str] = {"uri": self._uri}
            if self._token:
                client_kwargs["token"] = self._token
            client = MilvusClient(**client_kwargs)
            self._client = client
            if client.has_collection(self._collection_name):
                client.load_collection(self._collection_name)
                self._collection_ready = True

        await asyncio.to_thread(_connect)
        logger.info(
            "VectorStore connected",
            extra={"service": "vector_store", "provider": "milvus", "collection": self._collection_name,
                   "collection_exists": self._collection_ready,
                   "authenticated": bool(self._token)},
        )

    async def close(self) -> None:
        # MilvusClient 无常驻连接池需要显式关闭；置空引用释放资源
        self._client = None
        self._collection_ready = False

    def _require_client(self) -> MilvusClient:
        assert self._client is not None, "必须先调用 initialize()"
        return self._client

    # ---- 集合懒建 ----

    def _ensure_collection(self, dim: int) -> None:
        """按实际 embedding 维度创建集合（幂等；调用方需持有 _ensure_lock）。

        为什么在首次写入时才建：collection schema 必须声明稠密向量维度，
        而维度由 embedding 模型决定——从第一笔真实数据获取最可靠，
        避免配置项与模型漂移。
        """
        client = self._require_client()
        if self._collection_ready:
            return
        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("chunk_id", DataType.VARCHAR, is_primary=True, max_length=64)
        schema.add_field("document_id", DataType.VARCHAR, max_length=64)
        # content 启用 jieba 分词器：BM25 Function 用它做中文词面切分
        schema.add_field("content", DataType.VARCHAR, max_length=65535,
                         enable_analyzer=True, analyzer_params={"tokenizer": "jieba"})
        schema.add_field("chunk_index", DataType.INT64)
        schema.add_field("filename", DataType.VARCHAR, max_length=512)
        schema.add_field("dense", DataType.FLOAT_VECTOR, dim=dim)
        schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
        # 服务端 BM25：插入时按 content 自动生成稀疏表示，检索时把原始
        # 查询文本交给服务端分词打分——客户端零分词逻辑
        schema.add_function(Function(
            name="content_bm25",
            input_field_names=["content"],
            output_field_names=["sparse"],
            function_type=FunctionType.BM25,
        ))
        index_params = client.prepare_index_params()
        index_params.add_index(field_name="dense", index_type="AUTOINDEX", metric_type="COSINE")
        index_params.add_index(field_name="sparse", index_type="SPARSE_INVERTED_INDEX", metric_type="BM25")
        # document_id 上倒排索引：按文档删除是过滤删除的高频路径
        index_params.add_index(field_name="document_id", index_type="INVERTED")
        client.create_collection(
            self._collection_name, schema=schema, index_params=index_params,
            consistency_level="Strong",
        )
        self._collection_ready = True
        logger.info(
            "VectorStore collection created",
            extra={"service": "vector_store", "collection": self._collection_name, "dense_dim": dim},
        )

    # ---- 写入 ----

    async def add_chunks(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> list[str]:
        assert len(chunks) == len(embeddings), "chunk 与 embedding 必须一一对应"

        ids: list[str] = []
        rows: list[dict] = []
        for chunk, embedding in zip(chunks, embeddings):
            chunk.chunk_id = chunk.chunk_id or _new_chunk_id()
            ids.append(chunk.chunk_id)
            rows.append({
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "content": chunk.content,
                "chunk_index": chunk.chunk_index,
                # 稀疏向量由服务端 BM25 Function 从 content 生成，
                # metadata 只透传检索展示需要的来源字段
                "filename": str(chunk.metadata.get("filename", "未知来源")),
                "dense": embedding,
            })

        def _add() -> None:
            with self._ensure_lock:
                self._ensure_collection(len(embeddings[0]))
                self._require_client().insert(self._collection_name, rows)

        await asyncio.to_thread(_add)
        return ids

    # ---- 混合检索 ----

    async def hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        top_k: int = 4,
        min_score: float | None = None,
    ) -> list[RetrievedChunk]:
        """稠密 + 稀疏两路检索，服务端 RRF 融合。

        为什么 min_score 在这里实现：它是稠密通道的相似度下限，
        必须在融合之前由服务端 range search（radius）剔除弱命中；
        RRF 融合后的分数（量纲约 1/k）与余弦相似度不可比，无法事后过滤。
        min_score <= 0 时不加 radius：COSINE 的 range 过滤是严格大于，
        加 radius=0 会把相似度为 0 的结果也滤掉（实测确认）。
        """
        threshold = self._default_min_score if min_score is None else min_score

        def _search() -> list[RetrievedChunk]:
            client = self._require_client()
            if not self._collection_ready:
                return []
            dense_param: dict = {"metric_type": "COSINE"}
            if threshold > 0:
                dense_param["radius"] = threshold
            # 稠密通道候选上限：构造注入的 dense_top_k，与融合后 top_k 解耦
            dense_req = AnnSearchRequest(
                data=[query_embedding], anns_field="dense", param=dense_param,
                limit=max(1, self._dense_top_k),
            )
            # 稀疏通道直接传原始查询文本，分词与 BM25 打分都在服务端完成；
            # 候选上限同样由构造注入，确保两路召回量对称
            sparse_req = AnnSearchRequest(
                data=[query_text], anns_field="sparse", param={"metric_type": "BM25"},
                limit=max(1, self._bm25_top_k),
            )
            # RRF 融合：ranker 平滑常数由构造注入，融合后截断到 top_k
            result = client.hybrid_search(
                self._collection_name,
                reqs=[dense_req, sparse_req],
                ranker=RRFRanker(self._rrf_k),
                limit=max(1, top_k),
                output_fields=["document_id", "content", "filename", "chunk_index"],
                consistency_level="Strong",
            )
            hits: list[RetrievedChunk] = []
            for hit in result[0]:
                entity = hit.get("entity", {})
                # 主键以字段名（chunk_id）出现在结果中，而非固定键 "id"
                chunk = DocumentChunk(
                    chunk_id=str(hit["chunk_id"]),
                    document_id=str(entity.get("document_id", "")),
                    content=str(entity.get("content", "")),
                    chunk_index=int(entity.get("chunk_index", 0)),
                    metadata={"filename": str(entity.get("filename", "未知来源"))},
                )
                # distance 即 RRF 融合分数，保持"越大越相关"契约
                hits.append(RetrievedChunk(chunk=chunk, score=float(hit["distance"])))
            return hits

        return await asyncio.to_thread(_search)

    # ---- 删除 ----

    async def delete_by_document(self, document_id: str) -> int:
        def _delete() -> int:
            client = self._require_client()
            if not self._collection_ready:
                return 0
            # 先取计数再删除：Milvus 的 delete 不返回可靠的影响行数，
            # 而 count(*) 查询配合 INVERTED 索引代价可忽略
            counted = client.query(
                self._collection_name,
                filter=f'document_id == "{document_id}"',
                output_fields=["count(*)"],
            )
            removed = int(counted[0]["count(*)"]) if counted else 0
            if removed:
                client.delete(self._collection_name, filter=f'document_id == "{document_id}"')
            return removed

        return await asyncio.to_thread(_delete)
