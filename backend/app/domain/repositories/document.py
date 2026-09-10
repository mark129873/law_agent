"""DocumentRepository 抽象接口。

DDD 说明：文档仓储只管元数据的 CRUD 与状态更新——文本内容归 VectorStore
端口管，两个端口按聚合边界分离；update_status 单独成方法，是因为
"处理状态"是文档生命周期中唯一会被单独修改的属性。
"""

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
        """列出全部文档。

        契约说明（BE-024）：仓储不承诺顺序，文档列表的展示顺序
        （上传时间倒序，最新在前）由应用服务层决定。
        """

    @abstractmethod
    async def delete(self, document_id: str) -> bool:
        """删除文档元数据，返回是否实际删除。"""

    @abstractmethod
    async def update_status(self, document_id: str, status: DocumentStatus) -> bool:
        """更新文档处理状态，返回文档是否存在。"""
