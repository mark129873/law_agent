"""查询变体生成器基类（BE-034）：改写/子查询/扩展共用的模板方法骨架。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.agent.services.llm_service import LLMService
from app.agent.subgraphs.legal_rag.config import LegalRAGConfig
from app.agent.subgraphs.legal_rag.schemas import QueryVariants
from app.agent.subgraphs.legal_rag.state import LegalRAGState
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer
from app.domain.entities.llm import ChatMessage


class QueryVariantAgent(ABC):
    """查询变体生成器基类（模板方法模式）。

    为什么抽象基类：改写/子查询/扩展三个节点只有"提示词、状态键、
    数量上限"三点不同，"生成 → 容错解析 → 清洗截断 → 写状态"的
    骨架只写一份；新增变体节点时继承并提供三要素即可（开闭原则）。

    为什么解析失败安全默认为空列表：原始查询始终在检索队列中，
    查询变体是召回增强而非必需——变体失败只损失召回面，不中断流程
    （设计 §47 的安全默认精神在变体节点的应用）。
    """

    def __init__(self, llm: LLMService, config: LegalRAGConfig) -> None:
        self._llm = llm
        self._config = config

    @property
    @abstractmethod
    def _node_name(self) -> str:
        """节点名（trace 用）。"""

    @abstractmethod
    def _build_messages(
        self,
        original_query: str,
        normalized_query: str,
        missing_evidence: list[str],
    ) -> list[ChatMessage]:
        """组装本变体的提示消息。"""

    @abstractmethod
    def _state_key(self) -> str:
        """产出写入的状态键（各变体独立键，fan-out 并行写不冲突）。"""

    @abstractmethod
    def _max_queries(self) -> int:
        """本变体的数量上限（来自配置，设计 §23/§24/§25）。"""

    async def __call__(self, state: LegalRAGState) -> dict:
        timer = Timer()
        original = state.get("original_query") or ""
        normalized = state.get("normalized_query") or original
        missing_evidence = list(state.get("missing_evidence") or [])
        variants = await self._llm.structured_invoke(
            self._build_messages(original, normalized, missing_evidence),
            QueryVariants,
            default=QueryVariants(),
        )
        # 清洗：去空白、去空串、截断到上限
        cleaned = [q for q in (v.strip() for v in variants.queries) if q][: self._max_queries()]
        return {
            self._state_key(): cleaned,
            "rag_trace": [
                make_trace(
                    self._node_name,
                    "success",
                    timer.elapsed_ms(),
                    extra={"output_count": len(cleaned), "model": self._llm.model_name},
                )
            ],
        }
