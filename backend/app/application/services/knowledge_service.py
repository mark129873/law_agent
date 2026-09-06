"""知识库入库服务：Pipeline → Embedding → VectorStore 编排。

为什么独立成 Service：上传入库是完整的业务闭环（含日志与状态变更），
API 层只应调用它而不应拼装基础设施组件；
依赖全部来自抽象接口，任一环节可独立替换。
"""

from __future__ import annotations

import logging

from app.application.services.document_pipeline import DocumentPipeline
from app.domain.repositories.vector_store import VectorStore
from app.domain.services.embedding import EmbeddingService

logger = logging.getLogger("app.knowledge.ingestion")


class KnowledgeIngestionService:
    """将上传文档解析、向量化并写入向量知识库。"""

    def __init__(
        self,
        pipeline: DocumentPipeline,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
    ) -> None:
        self._pipeline = pipeline
        self._embedding = embedding_service
        self._vector_store = vector_store

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
