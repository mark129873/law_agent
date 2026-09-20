"""Tavily Remote MCP 与搜索留档单元测试（BE-048）。

所有远程调用都替换为 MCP ``CallToolResult`` 假对象：测试关注端口契约、
响应归一、安全脱敏和原子留档，不依赖网络、真实 API Key 或 Docker。
"""

import asyncio
import json
from pathlib import Path

import pytest
from mcp.types import CallToolResult, TextContent

from app.domain.services.web_search import (
    WEB_SEARCH_CONFIG_REQUIRED,
    WEB_SEARCH_EMPTY,
    WEB_SEARCH_LOG_WRITE_FAILED,
    WEB_SEARCH_SUCCESS,
)
from app.infrastructure.web_search.log_writer import WebSearchLogWriter
from app.infrastructure.web_search import tavily_mcp
from app.infrastructure.web_search.tavily_mcp import TavilyMcpSearchClient


def _response(*, structured=None, text="", is_error=False) -> CallToolResult:
    """构造 SDK v1 的工具结果，模拟 Tavily Remote MCP 返回格式。"""
    return CallToolResult(
        content=[TextContent(type="text", text=text)] if text else [],
        structuredContent=structured,
        isError=is_error,
    )


def test_mcp_call_uses_bearer_auth_and_tavily_arguments(monkeypatch: pytest.MonkeyPatch):
    """验证 SDK v1 Streamable HTTP 的地址、Bearer 头和工具参数。"""
    response = _response(structured={"results": []})
    observed: dict = {}

    class FakeHttpClient:
        def __init__(self, **kwargs):
            observed["http_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

    class FakeStream:
        def __init__(self, url, *, http_client):
            observed["url"] = url
            observed["http_client"] = http_client

        async def __aenter__(self):
            return "read", "write", "session-id"

        async def __aexit__(self, *_):
            return False

    class FakeSession:
        def __init__(self, read, write, *, read_timeout_seconds):
            observed["streams"] = (read, write)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def initialize(self):
            observed["initialized"] = True

        async def call_tool(self, name, *, arguments, read_timeout_seconds):
            observed["tool"] = (name, arguments)
            return response

    monkeypatch.setattr(tavily_mcp.httpx, "AsyncClient", FakeHttpClient)
    monkeypatch.setattr(tavily_mcp, "streamable_http_client", FakeStream)
    monkeypatch.setattr(tavily_mcp, "ClientSession", FakeSession)
    client = TavilyMcpSearchClient("https://mcp.tavily.com/mcp/", "tvly-secret")

    actual = asyncio.run(client._call_tool("最新法规"))

    assert actual is response
    assert observed["url"] == "https://mcp.tavily.com/mcp/"
    assert observed["http_kwargs"]["headers"] == {"Authorization": "Bearer tvly-secret"}
    assert observed["initialized"] is True
    assert observed["tool"] == (
        "tavily_search",
        {"query": "最新法规", "search_depth": "basic", "max_results": 5},
    )


def test_missing_key_is_logged_without_remote_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """未配置 Key 时生成配置状态和独立日志，但不创建远程 MCP 请求。"""
    client = TavilyMcpSearchClient("https://example.test/mcp", "", log_dir=tmp_path)

    async def should_not_call(_: str):
        raise AssertionError("missing key must not call Tavily")

    monkeypatch.setattr(client, "_call_tool", should_not_call)
    result = asyncio.run(client.search("最新法规", conversation_id="c"))

    assert result.status == WEB_SEARCH_CONFIG_REQUIRED
    assert result.error == "需要配置 TAVILY_API_KEY"
    assert len(list((tmp_path / "web_search").glob("search-*.log"))) == 1


def test_success_preserves_raw_and_normalized_results_in_one_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """成功响应：结构化结果进入规范化来源，完整原文与结构化体同文件留档。"""
    response = _response(
        structured={
            "results": [
                {
                    "title": "劳动法新闻",
                    "url": "https://example.com/law",
                    "content": "这是完整网页内容。",
                    "score": 0.91,
                },
                {
                    "title": "不安全地址",
                    "url": "javascript:alert(1)",
                    "content": "仍保留正文，但不能生成可点击的危险链接。",
                },
            ]
        },
        text="MCP 原始文本响应",
    )
    client = TavilyMcpSearchClient(
        "https://mcp.tavily.com/mcp/",
        "tvly-secret",
        log_dir=tmp_path,
    )

    async def fake_call(_: str):
        return response

    monkeypatch.setattr(client, "_call_tool", fake_call)
    result = asyncio.run(client.search("最新劳动法", conversation_id="conv-1"))

    assert result.status == WEB_SEARCH_SUCCESS
    assert len(result.results) == 2
    assert result.results[0].url == "https://example.com/law"
    assert result.results[1].url == ""
    files = sorted((tmp_path / "web_search").glob("search-*.log"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["query"] == "最新劳动法"
    assert payload["raw_response"]["structured_content"]["results"][0]["score"] == 0.91
    assert payload["results"][0]["content"] == "这是完整网页内容。"
    assert "tvly-secret" not in files[0].read_text(encoding="utf-8")
    assert not list((tmp_path / "web_search").glob("*.tmp"))


def test_text_response_is_normalized_and_each_call_gets_one_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """异常格式的文本结果也能提取 URL/标题/正文，连续两次调用生成两个文件。"""
    response = _response(
        text=(
            "1. 页面一\nURL: https://example.com/one\n"
            "Content: 第一条内容\n\n"
            "2. 页面二\nURL: https://example.com/two\n"
            "Content: 第二条内容\n"
        )
    )
    client = TavilyMcpSearchClient("https://example.test/mcp", "tvly-test", log_dir=tmp_path)

    async def fake_call(_: str):
        return response

    monkeypatch.setattr(client, "_call_tool", fake_call)
    first = asyncio.run(client.search("q1", conversation_id="c"))
    second = asyncio.run(client.search("q2", conversation_id="c"))

    assert first.results[0].title == "页面一"
    assert first.results[1].url == "https://example.com/two"
    assert second.status == WEB_SEARCH_SUCCESS
    assert len(list((tmp_path / "web_search").glob("search-*.log"))) == 2


def test_error_response_redacts_key_and_is_logged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """MCP 错误响应：错误状态落盘，但响应文本和错误字段都不泄漏 Key。"""
    response = _response(text="Authorization: Bearer tvly-secret", is_error=True)
    client = TavilyMcpSearchClient("https://example.test/mcp", "tvly-secret", log_dir=tmp_path)

    async def fake_call(_: str):
        return response

    monkeypatch.setattr(client, "_call_tool", fake_call)
    result = asyncio.run(client.search("q", conversation_id="c"))
    log_text = next((tmp_path / "web_search").glob("search-*.log")).read_text(encoding="utf-8")

    assert result.status != WEB_SEARCH_SUCCESS
    assert "tvly-secret" not in log_text
    assert "Bearer ***" in log_text


def test_empty_response_has_explicit_empty_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """没有结构化结果且文本无法解析时返回空结果状态，不编造来源。"""
    client = TavilyMcpSearchClient("https://example.test/mcp", "tvly-test", log_dir=tmp_path)

    async def fake_call(_: str):
        return _response(text="没有 URL 的说明")

    monkeypatch.setattr(client, "_call_tool", fake_call)
    result = asyncio.run(client.search("q", conversation_id="c"))
    assert result.status == WEB_SEARCH_EMPTY
    assert result.results == ()


def test_log_write_failure_is_a_search_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """留档失败时必须 fail-closed，避免用户看到“已搜索但未保存”。"""
    client = TavilyMcpSearchClient("https://example.test/mcp", "tvly-test", log_dir=tmp_path)

    async def fake_call(_: str):
        return _response(structured={"results": [{"title": "x", "url": "https://example.com", "content": "y"}]})

    def fail_write(_record):
        raise OSError("disk full")

    monkeypatch.setattr(client, "_call_tool", fake_call)
    monkeypatch.setattr(client._log_writer, "write", fail_write)
    result = asyncio.run(client.search("q", conversation_id="c"))
    assert result.status == WEB_SEARCH_LOG_WRITE_FAILED
    assert result.results
    assert "保存" in result.error


def test_writer_masks_sensitive_keys_and_writes_atomically(tmp_path: Path):
    """Writer 本身也做递归字段脱敏，并且目录中只留下最终 log 文件。"""
    writer = WebSearchLogWriter(tmp_path)
    target = writer.write({
        "authorization": "Bearer tvly-secret",
        "nested": {"api_key": "tvly-secret", "value": "完整内容"},
    })
    assert target.suffix == ".log"
    assert json.loads(target.read_text(encoding="utf-8"))["authorization"] == "***"
    assert "tvly-secret" not in target.read_text(encoding="utf-8")
    assert not list((tmp_path / "web_search").glob("*.tmp"))
