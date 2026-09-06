"""DocumentRepository 抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities.document import Document, DocumentStatus


class DocumentRepository(ABC):
    """知识库文档仓库契约。"""

    @abstractmethod
    async def create(self, document: Document) -> Document:
        """保存文档元数据并返回带 id 的实体。"""

    @abstractmethod
    async def get(self, document_id: str) -> Document | None:
        """按 id 查询文档，不存在返回 None。"""

    @abstractmethod
    async def list(self) -> list[Document]:
        """列出全部文档（按创建时间倒序）。"""

    @abstractmethod
    async def delete(self, document_id: str) -> bool:
        """删除文档元数据，返回是否实际删除。"""

    @abstractmethod
    async def update_status(self, document_id: str, status: DocumentStatus) -> bool:
        """更新文档处理状态，返回文档是否存在。"""
