"""子查询生成节点（BE-034，设计 §24）：把复杂问题拆分为独立子查询。"""

from __future__ import annotations

from app.agent.subgraphs.legal_rag.prompts.subquery_generator import build_subquery_messages
from app.agent.subgraphs.legal_rag.nodes._query_variant_base import QueryVariantAgent
from app.domain.entities.llm import ChatMessage


class SubqueryGeneratorAgent(QueryVariantAgent):
    """子查询拆分：按证据维度拆分、独立可检索（上限 max_subqueries=5）。"""

    @property
    def _node_name(self) -> str:
        return "subquery_generator_agent"

    def _build_messages(self, original_query: str, normalized_query: str) -> list[ChatMessage]:
        return build_subquery_messages(original_query, normalized_query)

    def _state_key(self) -> str:
        return "sub_queries"

    def _max_queries(self) -> int:
        return self._config.max_subqueries
