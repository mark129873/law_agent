"""证据转换工具（BE-032）：RetrievedChunk（端口契约）⇄ 证据条目（子图状态）。

为什么需要转换层：领域实体 RetrievedChunk 是 VectorStore 端口契约，
子图 EvidenceItem 是 Agent 内部结构；转换集中一处，端口演进时
不波及节点逻辑（防腐层，DDD）。
"""

from __future__ import annotations

from app.agent.subgraphs.legal_rag.state import EvidenceItem
from app.domain.entities.chunk import RetrievedChunk


def chunk_to_evidence(result: RetrievedChunk, query: str, query_type: str) -> EvidenceItem:
    """把端口检索结果转换为证据条目；rrf_score 承载服务端融合分。"""
    chunk = result.chunk
    filename = chunk.metadata.get("filename", "未知来源")
    return EvidenceItem(
        id=chunk.chunk_id or f"{chunk.document_id}:{chunk.chunk_index}",
        document_id=chunk.document_id,
        chunk_id=chunk.chunk_id,
        title=filename,
        content=chunk.content,
        query=query,
        query_type=query_type,
        rrf_score=result.score,
        source_name=filename,
        source_type=chunk.metadata.get("document_type", "law"),
        metadata=dict(chunk.metadata),
    )


def evidence_to_source(item: EvidenceItem) -> dict[str, str]:
    """证据条目 → SSE sources 事件条目（FE-011 参考文档展示契约）。"""
    return {
        "source": str(item.get("source_name") or item.get("title") or "未知来源"),
        "content": str(item.get("content") or ""),
    }


def format_evidence_context(items: list[EvidenceItem]) -> str:
    """证据列表 → LLM 上下文文本；空列表返回空串（衔接信息不足策略 BE-017）。

    为什么沿用【来源：文件名】格式：BE-017 回答策略与 grounding 规则
    都依赖该字面格式（回答注明来源、校验引用存在性），格式变更属
    行为变更，需同步 Prompt 与校验规则。
    """
    blocks = [
        f"【来源：{item.get('source_name') or item.get('title') or '未知来源'}】\n{item.get('content', '')}"
        for item in items
    ]
    return "\n\n".join(block for block in blocks if block.strip())
