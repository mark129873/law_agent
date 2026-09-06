"""DocumentChunk 领域实体。

DDD 说明：chunk 是向量检索的基本单元，本质是值对象——
它的同一性由内容与位置决定而非 id（chunk_id 仅为存储主键）；
DocumentChunk（写）与 RetrievedChunk（读，附加 score）拆成两个契约，
让"入库需要什么"与"检索返回什么"各自最小化（接口隔离）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DocumentChunk:
    """文档切片：向量库存储与检索单元。

    为什么 content 与 metadata 分离：content 参与向量检索与召回展示，
    metadata 只用于溯源（文件名、位置等），二者生命周期不同。
    """

    document_id: str
    content: str
    chunk_index: int = 0
    metadata: dict[str, str] = field(default_factory=dict)
    chunk_id: str = ""


@dataclass
class RetrievedChunk:
    """检索结果：命中 chunk 及其相似度得分。"""

    chunk: DocumentChunk
    # 相似度得分，实现方保证"越大越相关"
    score: float = 0.0
