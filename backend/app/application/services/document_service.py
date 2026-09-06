"""文档服务：知识库文档元数据与向量内容的业务管理。

为什么入库状态机放在 Service：上传结果是"元数据 + 向量"两侧的
最终一致性协议——解析失败时元数据必须标记 failed 而不是留下
processing 的僵尸记录，该规则只能有一处实现。
"""

from __future__ import annotations

import logging

from app.application.services.document_pipeline import DocumentParserFactory, UnsupportedFormatError
from app.application.services.knowledge_service import KnowledgeIngestionService
from app.domain.entities.document import Document, DocumentStatus
from app.infrastructure.database.base import Database
from app.domain.repositories.vector_store import VectorStore

logger = logging.getLogger("app.document.service")

# 上传大小上限（20MB）：防止超大文件阻塞事件循环与撑爆向量库
_MAX_UPLOAD_SIZE = 20 * 1024 * 1024


class DocumentTooLargeError(Exception):
    """上传文件超过大小上限。"""


class DocumentNotFoundError(Exception):
    """指定文档不存在。"""


class DocumentService:
    """知识库文档上传、查询与删除。"""

    def __init__(
        self,
        database: Database,
        parser_factory: DocumentParserFactory,
        ingestion_service: KnowledgeIngestionService,
        vector_store: VectorStore,
    ) -> None:
        self._db = database
        self._parser_factory = parser_factory
        self._ingestion = ingestion_service
        self._vector_store = vector_store

    async def upload_document(self, filename: str, content: bytes) -> Document:
        """上传并入库一个文档，返回最终状态为 ready/failed 的元数据。"""
        if len(content) > _MAX_UPLOAD_SIZE:
            raise DocumentTooLargeError(f"文件超过大小上限（{_MAX_UPLOAD_SIZE // (1024 * 1024)}MB）")
        # 格式识别前置：不支持的格式在创建任何元数据前就拒绝
        self._parser_factory.get_parser(filename)

        document = await self._db.documents.create(Document(filename=filename, file_size=len(content)))
        await self._db.documents.update_status(document.id, DocumentStatus.PROCESSING)
        logger.info(
            "Document upload started",
            extra={"service": "document", "document_id": document.id, "file_name": filename, "size": len(content)},
        )
        try:
            chunk_ids = await self._ingestion.ingest_document(document.id, filename, content)
            status = DocumentStatus.READY if chunk_ids else DocumentStatus.FAILED
            if not chunk_ids:
                logger.warning(
                    "Document produced no chunks",
                    extra={"service": "document", "document_id": document.id},
                )
        except Exception as error:
            # 解析/入库失败必须落库为 failed，调用方据此给用户失败反馈
            await self._db.documents.update_status(document.id, DocumentStatus.FAILED)
            logger.error(
                "Document ingestion failed",
                extra={"service": "document", "document_id": document.id, "error": str(error)},
            )
            raise
        await self._db.documents.update_status(document.id, status)
        logger.info(
            "Document upload completed",
            extra={"service": "document", "document_id": document.id, "status": status.value, "chunk_count": len(chunk_ids)},
        )
        document.status = status
        return document

    async def list_documents(self) -> list[Document]:
        return await self._db.documents.list()

    async def get_document(self, document_id: str) -> Document:
        document = await self._db.documents.get(document_id)
        if document is None:
            raise DocumentNotFoundError(f"文档不存在：{document_id}")
        return document

    async def delete_document(self, document_id: str) -> None:
        """删除文档：向量内容与元数据必须同时清理。"""
        await self.get_document(document_id)
        removed_chunks = await self._vector_store.delete_by_document(document_id)
        await self._db.documents.delete(document_id)
        logger.info(
            "Document deleted",
            extra={"service": "document", "document_id": document_id, "removed_chunks": removed_chunks},
        )
