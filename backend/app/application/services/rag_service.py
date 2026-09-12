"""RAG 检索服务：混合检索（向量 + BM25 关键词）与上下文构建的编排层。

为什么独立成 Service：检索是 Agent 与未来 API 共同依赖的业务能力，
集中在此处便于统一日志、缓存与重试策略；
依赖仅抽象接口，可整体替换 embedding、向量库或关键词索引实现。

混合检索（BE-028）：向量通道擅长语义相似（问法不同、含义相近），
BM25 关键词通道擅长法条编号、专有名词等词面精确匹配；两路结果用
Reciprocal Rank Fusion 融合——只看排名不看分数，规避 BM25 分数与
余弦相似度量纲不同、无法直接加权的问题。
"""

from __future__ import annotations

import logging
from dataclasses import replace

from app.domain.entities.chunk import RetrievedChunk
from app.domain.repositories.keyword_index import KeywordIndex
from app.domain.repositories.vector_store import VectorStore
from app.domain.services.embedding import EmbeddingService

logger = logging.getLogger("app.rag.retrieval")

# 检索结果在上下文中的来源标注格式，Agent Prompt 会引用它要求模型注明依据
_SOURCE_TEMPLATE = "【来源：{filename}】\n{content}"

# RRF 平滑常数（论文推荐值 60）：排名越靠前贡献越大，
# 同时避免排名第 1 与第 2 之间的得分差距过于悬殊
_RRF_K = 60


def reciprocal_rank_fusion(
    channels: list[list[RetrievedChunk]],
    top_k: int,
) -> list[RetrievedChunk]:
    """把多路检索结果按 RRF 融合排序（纯函数，无 IO）。

    融合规则：score(chunk) = Σ 1/(k + rank)，同一 chunk 在多路
    同时命中时得分叠加（天然去重且"两路都认为相关"的 chunk 排前）；
    结果对象的 score 统一改写为 RRF 得分，保持 RetrievedChunk
    "越大越相关"的契约。

    为什么拆成模块级纯函数：融合规则与 IO 无关，单独可测；
    与 format_context 同一拆分思路。
    """
    scores: dict[str, float] = {}
    # 同一 chunk 多路命中时保留首次（排名最靠前那路）的结果对象
    best: dict[str, RetrievedChunk] = {}
    for channel in channels:
        for rank, result in enumerate(channel, start=1):
            chunk_id = result.chunk.chunk_id
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank)
            best.setdefault(chunk_id, result)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[: max(1, top_k)]
    return [replace(best[chunk_id], score=score) for chunk_id, score in ranked]


class RagService:
    """根据用户问题从知识库混合检索相关法律知识。"""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        min_score: float = 0.0,
        keyword_index: KeywordIndex | None = None,
    ) -> None:
        self._embedding = embedding_service
        self._vector_store = vector_store
        # 相似度下限：低于该分数的向量命中视为不相关并丢弃。
        # 为什么默认 0.0：合适的阈值依赖具体 embedding 模型的分数分布，
        # 应结合真实模型实测后配置，而非拍脑袋写死。
        # 语义（BE-028 保持不变）：只过滤向量通道，在融合之前执行；
        # 关键词通道的 BM25 打分没有跨模型的量纲问题，不做阈值过滤
        # （0 分无效命中已由索引实现自身过滤）。
        self._min_score = min_score
        # 关键词通道：None 时退化为纯向量检索（优雅降级，
        # HYBRID_SEARCH_ENABLED=false 的回退路径也走这里）
        self._keyword_index = keyword_index

    async def retrieve(self, query: str, top_k: int = 4) -> list[RetrievedChunk]:
        """双通道检索并 RRF 融合，返回最相关的知识 chunk。"""
        # 通道一：向量语义检索（embed_query → 向量库近邻）
        vector_results = await self._vector_store.search(
            await self._embedding.embed_query(query), top_k=top_k
        )
        vector_results = [r for r in vector_results if r.score >= self._min_score]
        # 通道二：BM25 关键词词面检索（分词与打分由索引实现负责）
        keyword_results: list[RetrievedChunk] = []
        if self._keyword_index is not None:
            keyword_results = await self._keyword_index.search(query, top_k=top_k)
        fused = reciprocal_rank_fusion([vector_results, keyword_results], top_k=top_k)
        logger.info(
            "RAG hybrid retrieval completed",
            extra={
                "service": "rag",
                "query_length": len(query),
                "vector_hits": len(vector_results),
                "keyword_hits": len(keyword_results),
                "hit_count": len(fused),
                "top_score": fused[0].score if fused else 0.0,
            },
        )
        return fused

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
