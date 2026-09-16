"""联网搜索领域端口与结果值对象。

为什么把协议放在 domain：应用与 Agent 只需要知道“搜索一个问题并得到
网页结果”，不应该知道 MCP SDK、HTTP 客户端或 Tavily 的具体实现。
这是依赖倒置原则与防腐层的结合：基础设施适配器负责把外部数据转换成
本项目自己的值对象，未来替换搜索 Provider 时主图不需要改动。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# 能力状态使用字符串而不是基础设施异常，保证 CapabilityResult 可以统一
# 承载成功、空结果、配置缺失和远程故障等业务状态。
WEB_SEARCH_SUCCESS = "SUCCESS"
WEB_SEARCH_EMPTY = "WEB_SEARCH_EMPTY"
WEB_SEARCH_CONFIG_REQUIRED = "WEB_SEARCH_CONFIG_REQUIRED"
WEB_SEARCH_ERROR = "WEB_SEARCH_ERROR"
WEB_SEARCH_LOG_WRITE_FAILED = "WEB_SEARCH_LOG_WRITE_FAILED"


@dataclass(frozen=True)
class WebSearchItem:
    """一条已规范化的网页搜索结果。"""

    title: str
    url: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WebSearchResult:
    """一次搜索的完整结果值对象。

    raw_content 与 structured_content 只供后端留档和排障使用，不直接
    通过 SSE 返回；前端展示数据由 Agent 根据 WebSearchItem 生成 300 字预览。
    """

    search_id: str
    query: str
    status: str
    results: tuple[WebSearchItem, ...] = ()
    raw_content: tuple[str, ...] = ()
    structured_content: Any = None
    log_path: str = ""
    error: str = ""
    duration_ms: int = 0


@runtime_checkable
class WebSearchPort(Protocol):
    """联网搜索能力端口。

    生产实现通过 MCP 访问 Tavily，测试实现使用内存 Fake；调用方不依赖
    具体 SDK，符合接口隔离原则和项目 DDD 分层约束。
    """

    @property
    def configured(self) -> bool:
        """当前是否存在可用于认证的 Tavily API Key。"""

    async def search(self, query: str, *, conversation_id: str) -> WebSearchResult:
        """执行一次搜索并完成独立留档。"""
