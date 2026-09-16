"""引用构建服务（BE-033，设计 §41）：证据条目 → Citation 列表。"""

from __future__ import annotations

from app.agent.schemas import Citation
from app.agent.subgraphs.legal_rag.state import EvidenceItem
from app.agent.utils.dedup_utils import content_hash


class CitationService:
    """无状态转换服务：按证据顺序生成引用编号（[1][2]...）。"""

    def build_citations(self, evidence: list[EvidenceItem]) -> list[Citation]:
        """按证据顺序构建引用；同一 chunk 去重（先见优先）。

        为什么以证据顺序编号：final_answer_node 的引用整理与回答中的
        【来源：...】标注都基于同一批 ranked_evidence，顺序一致才能
        让引用号与来源一一对应。
        """
        citations: list[Citation] = []
        seen: set[str] = set()
        for item in evidence:
            document_id = str(item.get("document_id") or "")
            chunk_id = str(item.get("chunk_id") or "")
            chunk_index = item.get("metadata", {}).get("chunk_index", "")
            if chunk_id:
                key = chunk_id
            elif document_id or chunk_index != "":
                key = f"{document_id}:{chunk_index}"
            else:
                # Web 来源没有 document/chunk id，必须按正文哈希去重，
                # 不能把所有网页错误地合并成同一个空 id。
                key = f"hash:{content_hash(str(item.get('content') or ''))}"
            if key in seen:
                continue
            seen.add(key)
            metadata = item.get("metadata", {})
            citations.append(
                Citation(
                    citation_id=str(len(citations) + 1),
                    document_id=document_id,
                    chunk_id=chunk_id,
                    title=str(item.get("title") or ""),
                    source_name=str(item.get("source_name") or "") or None,
                    source_url=str(item.get("source_url") or "") or None,
                    article_number=metadata.get("article_number"),
                    metadata={},
                )
            )
        return citations
