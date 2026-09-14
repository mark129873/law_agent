"""统一重排服务：MiniLM CrossEncoder（BE-033，设计 §34）。

为什么依赖注入打分器而非直接持有 CrossEncoder：测试注入脚本化
打分器即可覆盖排序与降级逻辑，自动化测试不加载真实模型
（测试封闭性约束）；生产适配器 CrossEncoderScorer 负责懒加载与
线程池推理。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Protocol

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

    为什么有 enabled 开关：不同部署环境对 CPU/GPU 延迟的承受能力不同，
    关闭时仍保留 RRF 召回序，且通过 disabled 状态可观测；开启时使用
    配置注入的 CrossEncoder，模型加载或推理失败才进入 degraded 降级。
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


class CrossEncoderScorer:
    """CrossEncoder 适配器：懒加载单例 + 可配置设备推理。

    为什么懒加载：模型需要常驻内存，首次 rerank 才加载；asyncio.Lock
    防并发首次调用重复加载。为什么 to_thread：模型加载与推理都是阻塞
    调用，放线程池避免卡死事件循环（SSE 全异步）。
    """

    def __init__(self, model_path: str, device: str = "cpu") -> None:
        self._model_path = model_path
        self._device = device
        self._model: object | None = None
        self._lock = asyncio.Lock()

    async def _ensure_model(self) -> None:
        if self._model is None:
            async with self._lock:
                if self._model is None:  # 双重检查：锁内再验一次
                    from sentence_transformers import CrossEncoder  # 局部导入：重依赖仅此路径触达

                    logger.info(
                        "Agent reranker model loading",
                        extra={"service": "agent", "model_path": self._model_path, "device": self._device},
                    )
                    self._model = await asyncio.to_thread(
                        CrossEncoder, self._model_path, device=self._device
                    )
                    logger.info("Agent reranker model loaded", extra={"service": "agent"})

    async def score(self, query: str, documents: list[str]) -> list[float]:
        await self._ensure_model()
        pairs = [(query, document) for document in documents]
        scores = await asyncio.to_thread(self._model.predict, pairs)  # type: ignore[union-attr]
        return [float(value) for value in scores]
