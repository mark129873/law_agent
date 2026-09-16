"""Tavily Remote MCP 搜索适配器。

这里是全项目唯一接触 MCP SDK 的位置。适配器模式把 Tavily 的
CallToolResult 转换成 domain.WebSearchResult，并由独立 Writer 完成
一次一文件留档；Agent 节点只依赖 WebSearchPort。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.common.logging import get_request_id
from app.domain.services.web_search import (
    WEB_SEARCH_CONFIG_REQUIRED,
    WEB_SEARCH_EMPTY,
    WEB_SEARCH_ERROR,
    WEB_SEARCH_LOG_WRITE_FAILED,
    WEB_SEARCH_SUCCESS,
    WebSearchItem,
    WebSearchPort,
    WebSearchResult,
)
from app.infrastructure.web_search.log_writer import WebSearchLogWriter

logger = logging.getLogger("app.infrastructure.web_search")

_TOOL_NAME = "tavily_search"
_DEFAULT_TIMEOUT_SECONDS = 60.0
_URL_RE = re.compile(r"(?im)^\s*URL:\s*(https?://[^\s<>]+)")
_CONTENT_RE = re.compile(
    r"(?is)(?:^|\n)\s*(?:Content|Snippet|Description):\s*(.*?)(?=\n\s*(?:Raw Content|Score|Published Date|Title|URL):|\Z)"
)


class TavilyMcpSearchClient(WebSearchPort):
    """使用 Remote MCP Streamable HTTP 调用 Tavily 的客户端。"""

    def __init__(
        self,
        mcp_url: str,
        api_key: str,
        search_depth: str = "basic",
        max_results: int = 5,
        log_dir: str = "log",
    ) -> None:
        self._mcp_url = mcp_url.rstrip("/") + "/"
        self._api_key = api_key.strip()
        self._search_depth = search_depth
        self._max_results = max_results
        self._log_writer = WebSearchLogWriter(log_dir)

    @property
    def configured(self) -> bool:
        """只暴露是否配置，不暴露 Key 本身。"""
        return bool(self._api_key)

    async def search(self, query: str, *, conversation_id: str) -> WebSearchResult:
        """调用一次 tavily_search，并无论成败都尝试独立留档。"""
        search_id = uuid.uuid4().hex
        started_at = time.perf_counter()
        request_id = get_request_id()
        raw_response: dict[str, Any] = {}
        raw_content: tuple[str, ...] = ()
        structured_content: Any = None
        items: tuple[WebSearchItem, ...] = ()
        status = WEB_SEARCH_SUCCESS
        error = ""

        logger.info(
            "Web search started",
            extra={
                "service": "web_search",
                "search_id": search_id,
                "conversation_id": conversation_id,
                "query_length": len(query),
            },
        )

        try:
            if not self.configured:
                status = WEB_SEARCH_CONFIG_REQUIRED
                error = "需要配置 TAVILY_API_KEY"
            else:
                response = await self._call_tool(query)
                raw_response = _serialize_call_result(response)
                raw_content = tuple(
                    str(item.get("text") or "")
                    for item in raw_response.get("content", [])
                    if item.get("type") == "text"
                )
                structured_content = raw_response.get("structured_content")
                if raw_response.get("is_error"):
                    status = WEB_SEARCH_ERROR
                    error = self._redact_text("；".join(raw_content) or "Tavily MCP 返回错误")
                else:
                    items = tuple(_normalize_results(raw_content, structured_content))
                    status = WEB_SEARCH_SUCCESS if items else WEB_SEARCH_EMPTY
                    if status == WEB_SEARCH_EMPTY:
                        error = "Tavily 未返回可展示的网页结果"
        except Exception as exc:  # 远程连接、MCP 协议或响应解析异常统一转能力状态
            status = WEB_SEARCH_ERROR
            error = self._redact_text(str(exc) or exc.__class__.__name__)
            logger.exception(
                "Web search failed",
                extra={"service": "web_search", "search_id": search_id},
            )

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        safe_query = self._redact_text(query)
        # MCP 返回内容原则上不应包含认证信息，但远程错误回显并不受本地
        # 控制；在写入完整响应前再做一次值级脱敏，既保留排障原文，
        # 又满足“日志中不能出现 API Key/Authorization”的安全边界。
        safe_raw_response = self._redact_value(raw_response)
        safe_raw_content = [self._redact_text(item) for item in raw_content]
        safe_structured_content = self._redact_value(structured_content)
        safe_items = [
            self._redact_value(_item_to_dict(item))
            for item in items
        ]
        record = {
            "search_id": search_id,
            "timestamp": _utc_timestamp(),
            "request_id": request_id,
            "conversation_id": conversation_id,
            "query": safe_query,
            "tool_name": _TOOL_NAME,
            "arguments": {
                "query": safe_query,
                "search_depth": self._search_depth,
                "max_results": self._max_results,
            },
            "status": status,
            "duration_ms": duration_ms,
            "raw_response": safe_raw_response,
            "raw_content": safe_raw_content,
            "structured_content": safe_structured_content,
            "results": safe_items,
            "error": error,
        }
        log_path = ""
        try:
            # 文件写入可能涉及磁盘 IO，移出事件循环，避免阻塞其他 SSE 请求。
            written = await asyncio.to_thread(self._log_writer.write, record)
            log_path = str(written)
        except Exception as exc:
            # 用户明确要求“每次搜索必须落盘”，所以落盘失败不能伪装成成功。
            status = WEB_SEARCH_LOG_WRITE_FAILED
            error = "搜索结果无法保存到日志文件，请检查日志目录权限或磁盘空间"
            logger.exception(
                "Web search log write failed",
                extra={"service": "web_search", "search_id": search_id},
            )

        logger.info(
            "Web search completed",
            extra={
                "service": "web_search",
                "search_id": search_id,
                "status": status,
                "result_count": len(items),
                "duration_ms": duration_ms,
                "log_written": bool(log_path),
            },
        )
        return WebSearchResult(
            search_id=search_id,
            query=query,
            status=status,
            results=items,
            raw_content=raw_content,
            structured_content=structured_content,
            log_path=log_path,
            error=error,
            duration_ms=duration_ms,
        )

    async def _call_tool(self, query: str) -> Any:
        """创建一次短生命周期 MCP 会话并调用 tavily_search。"""
        timeout = httpx.Timeout(_DEFAULT_TIMEOUT_SECONDS, connect=10.0)
        headers = {"Authorization": f"Bearer {self._api_key}"}
        arguments = {
            "query": query,
            "search_depth": self._search_depth,
            "max_results": self._max_results,
        }
        async with httpx.AsyncClient(headers=headers, timeout=timeout) as http_client:
            async with streamable_http_client(self._mcp_url, http_client=http_client) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=timedelta(seconds=_DEFAULT_TIMEOUT_SECONDS),
                ) as session:
                    await session.initialize()
                    return await session.call_tool(
                        _TOOL_NAME,
                        arguments=arguments,
                        read_timeout_seconds=timedelta(seconds=_DEFAULT_TIMEOUT_SECONDS),
                    )

    def _redact_text(self, value: str) -> str:
        """从异常或远程错误文本中移除配置的 API Key。"""
        if self._api_key:
            value = value.replace(self._api_key, "***")
        # 有些 HTTP 异常会回显完整 Authorization 头，继续兜底掩掉其值。
        return re.sub(r"(?i)(Bearer\s+)[^\s,;]+", r"\1***", value)

    def _redact_value(self, value: Any) -> Any:
        """递归清理 MCP 原始响应中的密钥值和 Authorization 文本。"""
        if isinstance(value, dict):
            return {
                str(key): (
                    "***"
                    if any(
                        word in str(key).lower()
                        for word in ("api_key", "apikey", "authorization", "password", "secret", "token")
                    )
                    else self._redact_value(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact_value(item) for item in value]
        if isinstance(value, tuple):
            return [self._redact_value(item) for item in value]
        if isinstance(value, str):
            return self._redact_text(value)
        return value


def _utc_timestamp() -> str:
    """返回与标准结构化日志一致的 UTC 毫秒时间戳。"""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _json_safe(value: Any) -> Any:
    """把 MCP/Pydantic 对象转换成可写入 JSON 的普通对象。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_safe(model_dump(by_alias=True))
    return str(value)


def _serialize_call_result(response: Any) -> dict[str, Any]:
    """保留 CallToolResult 的完整字段，并补充内部统一读取别名。

    SDK 的 Pydantic 序列化结果可能使用 MCP 规范的 camelCase
    （structuredContent/isError）；保留该原始形状用于排障，同时补充
    snake_case 别名供归一化逻辑稳定读取，避免丢失 ``_meta`` 等字段。
    """
    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        raw = _json_safe(model_dump(by_alias=True))
        if isinstance(raw, dict):
            raw.setdefault("content", [])
            raw["structured_content"] = raw.get(
                "structuredContent", raw.get("structured_content")
            )
            raw["is_error"] = bool(raw.get("isError", raw.get("is_error", False)))
            return raw
    return {
        "content": [
            _json_safe(item)
            for item in (getattr(response, "content", None) or [])
        ],
        "structured_content": _json_safe(getattr(response, "structuredContent", None)),
        "is_error": bool(getattr(response, "isError", False)),
    }


def _normalize_results(raw_content: tuple[str, ...], structured_content: Any) -> list[WebSearchItem]:
    """优先解析结构化 results，失败时解析 Tavily 的文本格式。"""
    candidates = _structured_result_candidates(structured_content)
    if candidates:
        normalized = [_item_from_mapping(item) for item in candidates]
        return [item for item in normalized if item is not None]
    return _parse_text_results("\n\n".join(raw_content))


def _structured_result_candidates(value: Any) -> list[dict[str, Any]]:
    """兼容 MCP structuredContent 可能出现的 results/data/items 包装。"""
    if isinstance(value, dict):
        results = value.get("results")
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]
        for key in ("data", "items"):
            nested = _structured_result_candidates(value.get(key))
            if nested:
                return nested
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _item_from_mapping(item: dict[str, Any]) -> WebSearchItem | None:
    """从结构化结果提取标题、地址和正文；地址非法时不生成可点击链接。"""
    raw_url = str(item.get("url") or item.get("link") or "").strip()
    url = raw_url if _is_http_url(raw_url) else ""
    content = str(
        item.get("content")
        or item.get("raw_content")
        or item.get("snippet")
        or item.get("description")
        or ""
    ).strip()
    title = str(item.get("title") or item.get("name") or url or "网页来源").strip()
    if not content and not url:
        return None
    metadata = {
        key: _json_safe(value)
        for key, value in item.items()
        if key not in {"title", "name", "url", "link", "content", "raw_content", "snippet", "description"}
    }
    return WebSearchItem(title=title, url=url, content=content, metadata=metadata)


def _parse_text_results(text: str) -> list[WebSearchItem]:
    """解析 Tavily 当前文本输出中的 URL/Title/Content 区块。"""
    matches = list(_URL_RE.finditer(text))
    items: list[WebSearchItem] = []
    for index, match in enumerate(matches):
        block_start = matches[index - 1].end() if index else 0
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        prefix = text[block_start : match.start()]
        suffix = text[match.end() : block_end]
        url = match.group(1).rstrip(".,;)]}")
        title = _extract_title(prefix, url, index + 1)
        content_match = _CONTENT_RE.search(suffix)
        content = (content_match.group(1) if content_match else suffix).strip()
        content = re.sub(r"(?is)\n\s*Raw Content:.*\Z", "", content).strip()
        if _is_http_url(url) and (title or content):
            items.append(WebSearchItem(title=title, url=url, content=content))
    return items


def _extract_title(prefix: str, url: str, index: int) -> str:
    """从 URL 前的最后一行提取标题，并清理 Markdown 装饰。"""
    lines = [line.strip() for line in prefix.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.lower().startswith(("answer:", "detailed results:", "raw content:")):
            continue
        line = re.sub(r"^\s*\d+[.)]\s*", "", line)
        line = re.sub(r"^\*+|\*+$", "", line).strip()
        if line.lower().startswith("title:"):
            line = line.split(":", 1)[1].strip()
        if line and not line.lower().startswith("url:"):
            return line
    return urlparse(url).netloc or f"网页来源 {index}"


def _is_http_url(value: str) -> bool:
    """只允许 HTTP/HTTPS 地址进入前端链接。"""
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _item_to_dict(item: WebSearchItem) -> dict[str, Any]:
    """把领域值对象转换成日志 JSON。"""
    return {
        "title": item.title,
        "url": item.url,
        "content": item.content,
        "metadata": item.metadata,
    }
