"""RAG 检索服务：混合检索编排与上下文构建层。

为什么独立成 Service：检索是 Agent 与未来 API 共同依赖的业务能力，
集中在此处便于统一日志、缓存与重试策略；
依赖仅抽象接口，可整体替换 embedding 或向量库实现。

混合检索（BE-029）：稠密（语义）与稀疏 BM25（词面）两路检索及
RRF 融合由 Milvus 服务端一次 hybrid_search 完成——本服务只负责
查询向量化、阈值传递与结果整理，不感知融合算法细节
（BE-028 的自研 RRF 融合已随迁移删除）。
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
    """根据用户问题从知识库混合检索相关法律知识。"""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        min_score: float = 0.0,
    ) -> None:
        self._embedding = embedding_service
        self._vector_store = vector_store
        # 相似度下限：低于该分数的稠密通道命中视为不相关并剔除。
        # 为什么默认 0.0：合适的阈值依赖具体 embedding 模型的分数分布，
        # 应结合真实模型实测后配置，而非拍脑袋写死。
        # 语义（BE-029 保持不变）：只作用于稠密通道、在服务端 RRF
        # 融合之前执行（经 range search）；融合后的 RRF 分数不参与过滤。
        self._min_score = min_score

    async def retrieve(self, query: str, top_k: int = 4) -> list[RetrievedChunk]:
        """混合检索最相关的知识 chunk（服务端融合）。"""
        query_vector = await self._embedding.embed_query(query)
        results = await self._vector_store.hybrid_search(
            query, query_vector, top_k=top_k, min_score=self._min_score,
        )
        logger.info(
            "RAG hybrid retrieval completed",
            extra={
                "service": "rag",
                "query_length": len(query),
                "hit_count": len(results),
                "top_score": results[0].score if results else 0.0,
            },
        )
        return results

    async def retrieve_queries(
        self, queries: list[str], top_k_per_query: int = 4, max_chunks: int = 6
    ) -> list[RetrievedChunk]:
        """多子查询检索：逐条检索后按 chunk 合并去重（BE-030）。

        为什么在 Service 层合并而不是向量库层：子查询拆解是规划器
        的产物，"多路检索 + 去重"是业务编排，存储端口保持单查询
        契约不变；同一 chunk 被多个子查询命中说明相关度高，
        保留最高分（RRF 分数跨查询可比性有限，取 max 是保守策略）。
        合并后按分数排序截断到 max_chunks，控制 Prompt 上下文长度。
        """
        per_query: list[list[RetrievedChunk]] = []
        for query in queries:
            per_query.append(await self.retrieve(query, top_k=top_k_per_query))
        merged: dict[tuple, RetrievedChunk] = {}
        for results in per_query:
            for result in results:
                # 合并键：优先存储生成的 chunk_id；兜底 (document_id, chunk_index)
                # （两者组合在单文档内唯一，不依赖存储实现回填 chunk_id）
                key = (
                    result.chunk.chunk_id
                    or f"{result.chunk.document_id}:{result.chunk.chunk_index}"
                )
                existing = merged.get(key)
                if existing is None or result.score > existing.score:
                    merged[key] = result
        ordered = sorted(merged.values(), key=lambda r: r.score, reverse=True)[:max_chunks]
        logger.info(
            "RAG multi-query retrieval completed",
            extra={
                "service": "rag",
                "query_count": len(queries),
                "merged_hit_count": len(ordered),
            },
        )
        return ordered

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
