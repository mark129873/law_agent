"""统一重排服务：llama serve Qwen3 Reranker（BE-033，设计 §34）。

为什么依赖注入打分器而非把 HTTP 细节写进节点：测试注入脚本化打分器
即可覆盖排序与降级逻辑，自动化测试不访问真实模型；生产适配器
LlamaRerankScorer 只负责 HTTP 协议，服务异常由上层统一降级为 RRF。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.agent.subgraphs.legal_rag.state import EvidenceItem

logger = logging.getLogger("app.agent.services.reranker")


class RerankScorer(Protocol):
    """打分器抽象：给 (query, documents) 打相关性分（分数越高越相关）。"""

    async def score(self, query: str, documents: list[str]) -> list[float]: ...


@dataclass(frozen=True)
class RerankResult:
    """重排结果。

    `degraded` 只表示模型实际失败后的故障降级；`disabled` 表示用户
    通过配置主动关闭精排。两者都使用 RRF 顺序，但对用户提示和运行
    监控的含义不同，不能把“主动关闭”误报成“模型不可用”。
    """

    items: list[EvidenceItem]
    degraded: bool = False
    disabled: bool = False
    error: str = field(default="")


class RerankerService:
    """统一重排：以 original_query 对候选打分排序（设计约束 18）。

    为什么 final rerank 用 original_query 而不是某个 SubQuery（设计 §32）：
    SubQuery 用于召回覆盖，Original Query 才代表用户真实意图的
    最终相关性——多路召回、单口径精排。

    为什么有 enabled 开关：不同部署环境可能暂时不启动 Reranker 服务，
    关闭时仍保留 RRF 召回序，且通过 disabled 状态可观测；开启时使用
    配置注入的 llama serve 打分器，请求失败才进入 degraded 降级。
    """

    def __init__(self, scorer: RerankScorer, enabled: bool = True) -> None:
        self._scorer = scorer
        self._enabled = enabled

    async def rerank(
        self,
        query: str,
        documents: list[EvidenceItem],
        top_n: int,
    ) -> RerankResult:
        """重排并截断 top_n；任何打分异常都降级为原序（RRF 序）截断。"""
        if not documents:
            return RerankResult(items=[], degraded=False)
        if not self._enabled:
            logger.info(
                "Agent reranker disabled by configuration",
                extra={"service": "agent", "doc_count": len(documents)},
            )
            return RerankResult(
                items=documents[:top_n],
                disabled=True,
                error="rerank disabled by configuration (RERANK_ENABLED=false)",
            )
        try:
            scores = await self._scorer.score(
                query, [str(item.get("content") or "") for item in documents]
            )
            if len(scores) != len(documents):
                raise ValueError(
                    f"scorer returned {len(scores)} scores for {len(documents)} documents"
                )
        except Exception as error:  # noqa: BLE001——reranker 故障绝不阻断检索主链路
            logger.warning(
                "Agent reranker failed, degraded to RRF order",
                extra={"service": "agent", "error": str(error), "doc_count": len(documents)},
            )
            return RerankResult(items=documents[:top_n], degraded=True, error=str(error))

        # 为什么复制而不原地改：候选 dict 与图状态共享引用，原地写会污染归并前的数据
        scored: list[EvidenceItem] = [
            {**item, "rerank_score": float(score)} for item, score in zip(documents, scores)
        ]
        scored.sort(key=lambda item: item.get("rerank_score") or 0.0, reverse=True)
        return RerankResult(items=scored[:top_n], degraded=False)


class LlamaRerankScorer:
    """llama serve `/v1/rerank` 适配器。

    llama serve 返回按相关性排序的 ``results``，而 RerankerService 需要
    与输入文档同位的分数，因此这里按 ``index`` 还原为输入顺序。
    """

    def __init__(
        self,
        base_url: str,
        model_path: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_path = model_path
        # transport 仅供协议测试注入 MockTransport，生产路径保持 None。
        self._transport = transport

    async def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        logger.info(
            "Agent reranker requested",
            extra={
                "service": "agent",
                "provider": "llama",
                "model_path": self._model_path,
                "doc_count": len(documents),
            },
        )
        async with httpx.AsyncClient(timeout=120, transport=self._transport) as client:
            response = await client.post(
                f"{self._base_url}/v1/rerank",
                json={
                    "model": self._model_path,
                    "query": query,
                    "top_n": len(documents),
                    "documents": documents,
                },
            )
            response.raise_for_status()
            payload = response.json()

        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list) or len(results) != len(documents):
            raise ValueError("llama serve Reranker 响应数量不匹配")
        scores: list[float | None] = [None] * len(documents)
        try:
            for item in results:
                index = int(item["index"])
                if index < 0 or index >= len(documents) or scores[index] is not None:
                    raise ValueError("llama serve Reranker 响应 index 非法或重复")
                scores[index] = float(item["relevance_score"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("llama serve Reranker 响应格式非法") from error
        if any(score is None for score in scores):
            raise ValueError("llama serve Reranker 响应缺少文档分数")
        return [score for score in scores if score is not None]
