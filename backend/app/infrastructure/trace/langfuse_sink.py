"""Langfuse 可观测汇实现（BE-043，ADR-0010）。

为什么 langfuse SDK 锁在本目录：外部观测平台属基础设施细节，
领域层与应用层只依赖 domain/services/trace_sink.py 协议（DDD 守护
测试拦截越界导入）。

失败降级原则（与 BE-027 日志故障不阻断业务同一精神）：
- 构造期缺密钥 → 工厂 WARN 并退化为恒返回 None（等于关闭）；
- 运行期全部上报方法内部 try/except + WARN——Langfuse 不可达
  绝不把问答业务变成 5xx。
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.domain.services.trace_sink import TraceSink, TraceSpan

logger = logging.getLogger("app.infrastructure.trace")

# langfuse 延迟到本模块内部导入：关闭（工厂不构造）时零导入成本
from langfuse import Langfuse  # noqa: E402  —  本模块即 langfuse 隔离区


class LangfuseTraceSpan:
    """TraceSpan 的 langfuse 实现：包装一个 langfuse observation（span）。"""

    def __init__(self, span: Any) -> None:
        self._span = span

    def record_generation(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        output: str | None,
        duration_ms: int | None = None,
        error: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """记一次 LLM 调用为 generation（挂在本节点 span 下）。"""
        try:
            generation = self._span.start_observation(
                name="llm_call",
                as_type="generation",
                model=model,
                input=messages,
                output=output,
                metadata={
                    **(metadata or {}),
                    **({"duration_ms": str(duration_ms)} if duration_ms is not None else {}),
                },
                level="ERROR" if error else "DEFAULT",
                status_message=error,
            )
            generation.end()
        except Exception as error_:  # noqa: BLE001——可观测失败不阻断业务
            logger.warning("Langfuse generation report failed", extra={"service": "trace", "error": str(error_)})

    def end(self, *, duration_ms: int | None = None, error: str | None = None) -> None:
        """结束节点 span；异常路径以 ERROR 级别与原因留档。"""
        try:
            if error:
                self._span.update(level="ERROR", status_message=error)
            self._span.end()
        except Exception as error_:  # noqa: BLE001
            logger.warning("Langfuse span end failed", extra={"service": "trace", "error": str(error_)})


class LangfuseTraceSink:
    """TraceSink 的 langfuse 实现：每请求一个实例（工厂按请求创建）。

    线程/任务模型：_trace 在 start_trace 中赋值（先于图任务创建，
    happens-before 保证图任务可见）；节点 span 的父子关系由调用方
    （with_node_status）显式传 parent，不依赖跨任务可变栈。
    """

    def __init__(self, client: Langfuse) -> None:
        self._client = client
        self._trace: Any | None = None

    def start_trace(self, *, session_id: str, question: str) -> None:
        try:
            # 根 observation 即 UI 中的 trace；input=用户问题
            self._trace = self._client.start_observation(
                name="chat",
                input=question,
                metadata={"session_id": session_id},
            )
        except Exception as error:  # noqa: BLE001
            logger.warning("Langfuse trace start failed", extra={"service": "trace", "error": str(error)})

    def start_span(self, *, node: str, parent: TraceSpan | None = None) -> TraceSpan | None:
        # parent 优先（子图嵌套时由包装器显式传栈顶），否则挂 trace 根；
        # parent 是本模块的包装器时解包出底层 observation（同模块协作）
        if isinstance(parent, LangfuseTraceSpan):
            holder: Any = parent._span
        else:
            holder = parent if parent is not None else self._trace
        if holder is None:
            return None
        try:
            return LangfuseTraceSpan(holder.start_observation(name=node, as_type="span"))
        except Exception as error:  # noqa: BLE001
            logger.warning("Langfuse span start failed", extra={"service": "trace", "error": str(error)})
            return None

    def record_event(self, *, name: str, payload: dict[str, str]) -> None:
        if self._trace is None:
            return
        try:
            self._trace.create_event(name=f"flow:{name}", metadata=payload)
        except Exception as error:  # noqa: BLE001
            logger.warning("Langfuse event report failed", extra={"service": "trace", "error": str(error)})

    def end_trace(
        self,
        *,
        output: str | None = None,
        error: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        if self._trace is None:
            return
        try:
            self._trace.update(
                output=output if error is None else None,
                metadata=metadata,
                level="ERROR" if error else "DEFAULT",
                status_message=error,
            )
            self._trace.end()
        except Exception as error_:  # noqa: BLE001
            logger.warning("Langfuse trace end failed", extra={"service": "trace", "error": str(error_)})


class LangfuseTraceSinkFactory:
    """按请求创建 sink 的工厂；客户端懒初始化单例（DIP 装配点消费）。"""

    def __init__(self, *, base_url: str, public_key: str, secret_key: str) -> None:
        self._client: Langfuse | None = None
        if not public_key or not secret_key:
            # 与 GLM 缺密钥不同：trace 是可观测增强，缺配置降级而非启动失败
            logger.warning(
                "Langfuse enabled but keys missing, tracing disabled",
                extra={"service": "trace", "langfuse_base_url": base_url},
            )
            return
        try:
            self._client = Langfuse(public_key=public_key, secret_key=secret_key, host=base_url)
            logger.info(
                "Langfuse tracing enabled",
                extra={"service": "trace", "langfuse_base_url": base_url},
            )
        except Exception as error:  # noqa: BLE001
            logger.warning("Langfuse client init failed, tracing disabled", extra={"service": "trace", "error": str(error)})

    def create(self) -> TraceSink | None:
        """每问答请求一个新 sink（trace 生命周期 = 请求生命周期）。"""
        if self._client is None:
            return None
        return LangfuseTraceSink(self._client)

    # 让实例满足 TraceSinkFactory（Callable[[], TraceSink | None]）口径：
    # containers 直接注入实例，ChatService 按可调用对象使用
    __call__ = create


def null_trace_sink_factory() -> TraceSink | None:
    """关闭态工厂：恒返回 None（所有上报点跳过，零 langfuse 开销）。"""
    return None


# 工厂的统一类型口径：containers 装配与 ChatService 注入都用它
TraceSinkFactory = Callable[[], TraceSink | None]
