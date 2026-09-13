"""LLM 服务：Agent 图统一的模型调用入口（BE-033，设计 §39；BE-043 generation 采集）。

为什么节点不直接用 LLMProvider（设计约束 24）：所有节点经同一服务
调用模型，结构化输出的"容错解析 + 重试 + 安全默认"策略只实现一份
（设计 §47），调优不会遗漏某个节点；同理，Langfuse generation 也只在
这一处记录——三条调用路径（invoke/structured_invoke/stream）一次接入
全覆盖。
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.agent.trace_context import current_trace_span
from app.agent.utils.timing_utils import Timer
from app.domain.entities.llm import ChatMessage, LlmParams
from app.domain.entities.message import MessageRole
from app.domain.repositories.llm_provider import LLMProvider

logger = logging.getLogger("app.agent.services.llm")

_SchemaT = TypeVar("_SchemaT", bound=BaseModel)

# 结构化输出失败的重试次数（设计 §47：允许重试 1 次）
STRUCTURED_MAX_RETRIES = 1


def extract_json_block(raw: str) -> Any:
    """从模型原始输出中提取第一个 JSON 值（纯函数，容错优先）。

    为什么做容错：小模型常把 JSON 包在 ```json 代码块里、或在前后
    带解释文字；逐字符扫描括号配对（字符串感知）比"掐头去尾"更稳。
    提取失败返回 None，由调用方决定重试或安全默认。
    """
    text = raw.strip()
    if not text:
        return None
    # 容忍 ```json ... ``` 代码块包裹
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    # 扫描第一个平衡的 {...} 或 [...]（忽略字符串内的括号）
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : index + 1])
                    except (json.JSONDecodeError, ValueError):
                        break
    return None


def parse_structured_output(raw: str, schema: type[_SchemaT]) -> _SchemaT | None:
    """把模型输出解析为指定 Schema；不可解析返回 None（纯函数）。"""
    data = extract_json_block(raw)
    if data is None:
        return None
    try:
        return schema.model_validate(data)
    except ValidationError:
        return None


class LLMService:
    """模型调用服务：普通调用 + 结构化调用（安全默认兜底）。"""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    @property
    def model_name(self) -> str:
        """当前模型名（日志与 trace 用，不含密钥）。"""
        return self._provider.model_name

    def _serialize_messages(self, messages: list[ChatMessage]) -> list[dict[str, str]]:
        """领域消息 → 中立 dict（Langfuse 的 generation input）。"""
        return [
            {"role": m.role.value if isinstance(m.role, MessageRole) else str(m.role), "content": m.content}
            for m in messages
        ]

    def _record_generation(
        self,
        messages: list[ChatMessage],
        *,
        output: str | None,
        duration_ms: int | None = None,
        error: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """向当前节点 span 记一条 generation（BE-043）。

        为什么读上下文而不是注入：LLM 调用发生在图任务内的当前节点
        span 下，经 trace_context 的 ContextVar 取父级——与节点包装器
        压栈同上下文，嵌套关系确定；无 span（未启用/图外直调）时跳过。
        """
        span = current_trace_span()
        if span is None:
            return
        span.record_generation(
            model=self.model_name,
            messages=self._serialize_messages(messages),
            output=output,
            duration_ms=duration_ms,
            error=error,
            metadata=metadata,
        )

    async def invoke(
        self, messages: list[ChatMessage], params: LlmParams | None = None
    ) -> str:
        """普通文本调用（透传 Provider）。"""
        timer = Timer()
        try:
            answer = await self._provider.chat(messages, params)
        except Exception as error:
            self._record_generation(messages, output=None, error=str(error))
            raise
        self._record_generation(messages, output=answer, duration_ms=timer.elapsed_ms())
        return answer

    def stream(self, messages: list[ChatMessage], params: LlmParams | None = None):
        """流式调用（透传 Provider，逐增量产出；完成后记一条 generation）。

        为什么定义为普通方法返回异步迭代器：与 LLMProvider.stream
        同一书写约定，`async for chunk in service.stream(...)` 即用。
        为什么包一层生成器：增量必须聚合后才构成 generation 的 output，
        异常路径也要把已产出片段与错误记档（BE-043）。
        """
        return self._traced_stream(messages, params)

    async def _traced_stream(self, messages: list[ChatMessage], params: LlmParams | None):
        span = current_trace_span()
        if span is None:
            # 未启用 trace：纯透传，零额外开销
            async for chunk in self._provider.stream(messages, params):
                yield chunk
            return
        timer = Timer()
        chunks: list[str] = []
        try:
            async for chunk in self._provider.stream(messages, params):
                chunks.append(chunk)
                yield chunk
        except Exception as error:
            self._record_generation(
                messages, output="".join(chunks), error=str(error), metadata={"mode": "stream"}
            )
            raise
        self._record_generation(
            messages, output="".join(chunks), duration_ms=timer.elapsed_ms(), metadata={"mode": "stream"}
        )

    async def structured_invoke(
        self,
        messages: list[ChatMessage],
        schema: type[_SchemaT],
        *,
        default: _SchemaT,
        max_retries: int = STRUCTURED_MAX_RETRIES,
    ) -> _SchemaT:
        """结构化调用：解析失败重试 1 次，仍失败返回安全默认（设计 §47）。

        为什么由调用方传入 default：安全默认是业务决策（Planner 默认
        original、Grader 默认 insufficient——宁可多检索不可误判充分），
        服务层不该替业务拍板；重试时附修正指令，比原样重发成功率更高。
        每次尝试各记一条 generation（attempt/metadata 区分，BE-043）。
        """
        current: list[ChatMessage] = list(messages)
        parsed: _SchemaT | None = None
        for attempt in range(max_retries + 1):
            timer = Timer()
            try:
                raw = await self._provider.chat(current)
            except Exception as error:
                self._record_generation(
                    current, output=None, error=str(error),
                    metadata={"attempt": str(attempt + 1), "schema": schema.__name__},
                )
                raise
            parsed = parse_structured_output(raw, schema)
            self._record_generation(
                current,
                output=raw,
                duration_ms=timer.elapsed_ms(),
                metadata={
                    "attempt": str(attempt + 1),
                    "schema": schema.__name__,
                    "parsed": "true" if parsed is not None else "false",
                },
            )
            if parsed is not None:
                return parsed
            logger.warning(
                "Agent structured output unparsable",
                extra={
                    "service": "agent",
                    "model": self._provider.model_name,
                    "attempt": attempt + 1,
                    "raw_length": len(raw),
                },
            )
            # 追加修正指令后重试（最后一次失败不再追加，直接走默认）
            current = list(messages) + [
                ChatMessage(
                    role=MessageRole.USER,
                    content="上一次输出不是合法 JSON。请只输出符合要求的 JSON，不要包含任何解释或代码块以外的内容。",
                )
            ]
        logger.warning(
            "Agent structured output failed, using safe default",
            extra={"service": "agent", "model": self._provider.model_name, "schema": schema.__name__},
        )
        return default
