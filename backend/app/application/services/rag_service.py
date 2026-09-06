"""RAG 检索服务：查询向量化与知识库检索的编排层。

为什么独立成 Service：检索是 Agent 与未来 API 共同依赖的业务能力，
集中在此处便于统一日志、缓存与重试策略；
依赖仅抽象接口，可整体替换 embedding 或向量库实现。
"""

from __future__ import annotations

import logging

from app.domain.entities.chunk import RetrievedChunk
from app.domain.repositories.vector_store import VectorStore
from app.domain.services.embedding import EmbeddingService

logger = logging.getLogger("app.rag.retrieval")

# 检索结果在上下文中的来源标注格式，Agent Prompt 会引用它要求模型注明依据
_SOURCE_TEMPLATE = "【来源：{filename}】\n{content}"


class RagService:
    """根据用户问题从知识库检索相关法律知识。"""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        min_score: float = 0.0,
    ) -> None:
        self._embedding = embedding_service
        self._vector_store = vector_store
        # 相似度下限：低于该分数的命中视为不相关并丢弃。
        # 为什么默认 0.0：合适的阈值依赖具体 embedding 模型的分数分布，
        # 应结合真实模型实测后配置，而非拍脑袋写死。
        self._min_score = min_score

    async def retrieve(self, query: str, top_k: int = 4) -> list[RetrievedChunk]:
        """向量化查询并检索最相关的知识 chunk。"""
        query_vector = await self._embedding.embed_query(query)
        results = await self._vector_store.search(query_vector, top_k=top_k)
        filtered = [r for r in results if r.score >= self._min_score]
        logger.info(
            "RAG retrieval completed",
            extra={
                "service": "rag",
                "query_length": len(query),
                "hit_count": len(filtered),
                "top_score": filtered[0].score if filtered else 0.0,
            },
        )
        return filtered

    async def build_context(self, query: str, top_k: int = 4) -> str:
        """检索并格式化为 LLM 上下文文本；知识库无相关内容时返回空串。

        为什么返回空串而不是占位文案：空串让上层 Prompt 策略
        （BE-017）能够明确区分"有依据"与"无依据"两种路径。
        """
        results = await self.retrieve(query, top_k=top_k)
        return self.format_context(results)

    def format_context(self, results: list[RetrievedChunk]) -> str:
        """把检索结果格式化为 LLM 上下文文本（纯函数，无 IO）。

        为什么从 build_context 拆出：检索节点（RetrieveNode）需要
        "检索 + 格式化"分开两步——格式化结果进 Prompt 的同时，
        还要用同一批 chunk 组装参考来源事件推送给前端（FE-011）；
        拆出后 Prompt 上下文与参考文档展示天然同源，不会各写一份格式化。
        """
        if not results:
            return ""
        return "\n\n".join(
            _SOURCE_TEMPLATE.format(
                filename=result.chunk.metadata.get("filename", "未知来源"),
                content=result.chunk.content,
            )
            for result in results
        )
