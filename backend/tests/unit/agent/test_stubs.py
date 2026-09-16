"""Web/Plugin 能力单元测试（BE-037/BE-048）。

BE-037 现在只保留 Plugin Stub；联网搜索由 Tavily MCP 端口执行，
因此本文件同时锁定按钮关闭、配置缺失、成功结果和插件未实现契约。
"""

import asyncio

from app.agent.constants import (
    CAPABILITY_DISABLED,
    CAPABILITY_NOT_IMPLEMENTED,
    CAPABILITY_SUCCESS,
    CAPABILITY_WEB_SEARCH_CONFIG_REQUIRED,
    CAPABILITY_WEB_SEARCH_LOG_WRITE_FAILED,
)
from app.agent.plugins import PluginEntryNode, PluginStubNode
from app.agent.state import AgentState
from app.agent.web import WebSearchEntryNode
from app.domain.services.web_search import WebSearchItem, WebSearchResult


def _state(**overrides) -> AgentState:
    base: AgentState = {"question": "帮我搜一下最新法规"}
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


class FakeWebSearchPort:
    """内存搜索端口：测试图节点，不触网也不依赖 MCP SDK。"""

    configured = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def search(self, query: str, *, conversation_id: str) -> WebSearchResult:
        self.calls.append((query, conversation_id))
        return WebSearchResult(
            search_id="search-test",
            query=query,
            status=CAPABILITY_SUCCESS,
            results=(WebSearchItem("Tavily 页面", "https://example.com/law", "网页正文"),),
        )


def test_web_entry_disabled_by_default():
    port = FakeWebSearchPort()
    result = asyncio.run(WebSearchEntryNode(port)(_state(web_search_requested=False)))
    assert result["capability_result"]["status"] == CAPABILITY_DISABLED
    assert port.calls == []  # 按钮关闭时绝不调用 MCP


def test_web_entry_missing_port_returns_config_notice():
    result = asyncio.run(WebSearchEntryNode()(_state(web_search_requested=True)))
    assert result["capability_result"]["status"] == CAPABILITY_WEB_SEARCH_CONFIG_REQUIRED


def test_web_entry_success_normalizes_port_result():
    port = FakeWebSearchPort()
    result = asyncio.run(
        WebSearchEntryNode(port)(
            _state(web_search_requested=True, normalized_query="劳动法最新变化", conversation_id="conv-1")
        )
    )
    capability = result["capability_result"]
    assert capability["status"] == CAPABILITY_SUCCESS
    assert capability["evidence"][0]["source_url"] == "https://example.com/law"
    assert port.calls == [("劳动法最新变化", "conv-1")]


def test_web_entry_drops_results_when_persistence_failed():
    """搜索日志落盘失败时，结果不得继续进入回答和来源展示链。"""

    class FailedPersistencePort(FakeWebSearchPort):
        async def search(self, query: str, *, conversation_id: str) -> WebSearchResult:
            return WebSearchResult(
                search_id="failed-log",
                query=query,
                status=CAPABILITY_WEB_SEARCH_LOG_WRITE_FAILED,
                results=(WebSearchItem("不应展示", "https://example.com", "不应进入回答"),),
                error="搜索结果无法保存到日志文件",
            )

    result = asyncio.run(WebSearchEntryNode(FailedPersistencePort())(_state(web_search_requested=True)))
    assert result["capability_result"]["status"] == CAPABILITY_WEB_SEARCH_LOG_WRITE_FAILED
    assert result["capability_result"]["evidence"] == []


def test_plugin_entry_then_stub_not_implemented():
    asyncio.run(PluginEntryNode()(_state()))
    result = asyncio.run(PluginStubNode()(_state()))
    assert result["capability_result"]["capability"] == "plugin"
    assert result["capability_result"]["status"] == CAPABILITY_NOT_IMPLEMENTED
    assert result["capability_result"]["evidence"] == []
