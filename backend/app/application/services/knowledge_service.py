"""知识库入库服务：Pipeline → Embedding → 向量库 + 关键词索引 双写编排。

为什么独立成 Service：上传入库是完整的业务闭环（含日志与状态变更），
API 层只应调用它而不应拼装基础设施组件；
依赖全部来自抽象接口，任一环节可独立替换。

双写（BE-028）：chunk 同时写入向量库（语义检索用）与关键词索引
（BM25 词面检索用）；两路存储的一致性由本服务这一处编排保证，
调用方不需要感知"知识库其实有两份索引"。
"""

from __future__ import annotations

import logging

from app.application.services.document_pipeline import DocumentPipeline
from app.domain.repositories.keyword_index import KeywordIndex
from app.domain.repositories.vector_store import VectorStore
from app.domain.services.embedding import EmbeddingService

logger = logging.getLogger("app.knowledge.ingestion")


class KnowledgeIngestionService:
    """将上传文档解析、向量化并写入向量知识库与关键词索引。"""

    def __init__(
        self,
        pipeline: DocumentPipeline,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        keyword_index: KeywordIndex | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._embedding = embedding_service
        self._vector_store = vector_store
        # 关键词索引可选：None 时只写向量库（混合检索关闭的回退路径）
        self._keyword_index = keyword_index

    async def ingest_document(
        self,
        document_id: str,
        filename: str,
        content: bytes,
    ) -> list[str]:
        """处理并入库一个文档，返回写入的 chunk id 列表。

        document_id 由调用方分配（通常来自 DocumentRepository 保存的元数据），
        用于后续按文档删除知识库内容。
        """
        logger.info(
            "Knowledge ingestion started",
            extra={"service": "knowledge", "document_id": document_id, "file_name": filename, "size": len(content)},
        )
        # 1. 解析/清洗/切分
        chunks = await self._pipeline.process(filename, content)
        if not chunks:
            logger.warning(
                "Knowledge ingestion produced no chunks",
                extra={"service": "knowledge", "document_id": document_id, "file_name": filename},
            )
            return []

        # 2. 回填 document_id，保证向量库中的 chunk 可按文档溯源与删除
        for chunk in chunks:
            chunk.document_id = document_id

        # 3. 批量向量化后写入向量库
        vectors = await self._embedding.embed_documents([chunk.content for chunk in chunks])
        chunk_ids = await self._vector_store.add_chunks(chunks, vectors)

        # 4. 双写关键词索引（BM25 词面检索用）。
        # 必须放在向量库写入之后：Chroma 的 add_chunks 会为无 id 的
        # chunk 补生成主键，关键词索引复用同一批 id 才能保证两路
        # 检索结果的 chunk_id 一致（RRF 融合依赖它去重）
        if self._keyword_index is not None:
            await self._keyword_index.add_chunks(chunks)

        logger.info(
            "Knowledge ingestion completed",
            extra={
                "service": "knowledge",
                "document_id": document_id,
                "file_name": filename,
                "chunk_count": len(chunk_ids),
            },
        )
        return chunk_ids
