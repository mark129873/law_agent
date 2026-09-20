"""查询扩展节点（BE-034，设计 §25）：补充法律术语与同义表述。"""

from __future__ import annotations

from app.agent.subgraphs.legal_rag.prompts.query_expansion import build_expansion_messages
from app.agent.subgraphs.legal_rag.nodes._query_variant_base import QueryVariantAgent
from app.domain.entities.llm import ChatMessage


class QueryExpansionAgent(QueryVariantAgent):
    """查询扩展：法律术语/同义词/裁判文书表述（上限 max_expanded_queries=3）。"""

    @property
    def _node_name(self) -> str:
        return "query_expansion_agent"

    def _build_messages(
        self,
        original_query: str,
        normalized_query: str,
        missing_evidence: list[str],
    ) -> list[ChatMessage]:
        return build_expansion_messages(original_query, normalized_query, missing_evidence)

    def _state_key(self) -> str:
        return "expanded_queries"

    def _max_queries(self) -> int:
        return self._config.max_expanded_queries
