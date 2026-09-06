"""DocumentChunk 领域实体。"""

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
