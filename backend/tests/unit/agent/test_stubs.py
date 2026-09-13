"""Web/Plugin Stub 单元测试（BE-037）。

覆盖开关判定、透传语义与 NOT_IMPLEMENTED 契约（设计 §15/§16）。
"""

import asyncio

from app.agent.constants import CAPABILITY_DISABLED, CAPABILITY_NOT_IMPLEMENTED
from app.agent.plugins import PluginEntryNode, PluginStubNode
from app.agent.state import AgentState
from app.agent.web import WebSearchEntryNode, WebSearchStubNode


def _state(**overrides) -> AgentState:
    base: AgentState = {"question": "帮我搜一下最新法规"}
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


def test_web_entry_disabled_by_default():
    result = asyncio.run(WebSearchEntryNode()(_state(web_search_enabled=False)))
    assert result["capability_result"]["status"] == CAPABILITY_DISABLED


def test_web_entry_enabled_continues_to_stub():
    result = asyncio.run(WebSearchEntryNode()(_state(web_search_enabled=True)))
    assert "capability_result" not in result  # 不产出结果，继续进 Stub


def test_web_stub_returns_not_implemented_when_enabled():
    result = asyncio.run(WebSearchStubNode()(_state(web_search_enabled=True)))
    assert result["capability_result"]["status"] == CAPABILITY_NOT_IMPLEMENTED


def test_web_stub_passthrough_disabled_result():
    disabled_result = asyncio.run(WebSearchEntryNode()(_state(web_search_enabled=False)))
    state = _state(web_search_enabled=False, capability_result=disabled_result["capability_result"])
    result = asyncio.run(WebSearchStubNode()(state))
    assert result["capability_result"]["status"] == CAPABILITY_DISABLED  # 透传不覆盖


def test_plugin_entry_then_stub_not_implemented():
    asyncio.run(PluginEntryNode()(_state()))
    result = asyncio.run(PluginStubNode()(_state()))
    assert result["capability_result"]["capability"] == "plugin"
    assert result["capability_result"]["status"] == CAPABILITY_NOT_IMPLEMENTED
    assert result["capability_result"]["evidence"] == []
