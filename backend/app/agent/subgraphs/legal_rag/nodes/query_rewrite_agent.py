"""查询改写节点（BE-034，设计 §23）：改写为更适合本地检索的查询。"""

from __future__ import annotations

from app.agent.subgraphs.legal_rag.prompts.query_rewrite import build_rewrite_messages
from app.agent.subgraphs.legal_rag.nodes._query_variant_base import QueryVariantAgent
from app.domain.entities.llm import ChatMessage


class QueryRewriteAgent(QueryVariantAgent):
    """查询改写：补全省略要素、生活用语换法律术语（上限 max_rewritten_queries=2）。"""

    @property
    def _node_name(self) -> str:
        return "query_rewrite_agent"

    def _build_messages(
        self,
        original_query: str,
        normalized_query: str,
        missing_evidence: list[str],
    ) -> list[ChatMessage]:
        return build_rewrite_messages(original_query, normalized_query, missing_evidence)

    def _state_key(self) -> str:
        return "rewritten_queries"

    def _max_queries(self) -> int:
        return self._config.max_rewritten_queries
