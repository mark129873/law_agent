"""Document 领域实体。

DDD 说明：Document 只承载知识库文档的元数据（id/文件名/大小/状态），
文本内容本身存放在向量数据库——实体与它聚合不到一起的外部大对象分离，
是"聚合边界最小化"的体现。status 状态机（pending/processing/ready/failed）
表达文档从接收到可检索的完整生命周期，非法状态转移由状态枚举约束。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.domain.entities.conversation import utc_now


class DocumentStatus(str, Enum):
    """知识库文档处理状态，与文档处理 Pipeline 的阶段对应。"""

    PENDING = "pending"          # 已接收，等待解析入库
    PROCESSING = "processing"    # 解析/分块/向量化进行中
    READY = "ready"              # 入库完成，可被检索
    FAILED = "failed"            # 处理失败


@dataclass
class Document:
    """知识库文档元数据；文本内容本身存放在向量数据库中。"""

    filename: str
    file_size: int
    status: DocumentStatus = DocumentStatus.PENDING
    id: str = ""
    created_at: datetime = field(default_factory=utc_now)
