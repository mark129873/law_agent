"""联网搜索能力节点（BE-048）。

节点只负责把前端的显式请求交给领域端口，并把领域值对象转换为统一
CapabilityResult。MCP SDK、HTTP 和独立日志写入都封装在基础设施适配器
中，符合单一职责、依赖倒置与 DDD 防腐层原则。
"""

from __future__ import annotations

from app.agent.constants import (
    CAPABILITY_SUCCESS,
    CAPABILITY_DISABLED,
    CAPABILITY_WEB_SEARCH_CONFIG_REQUIRED,
    CAPABILITY_WEB_SEARCH_EMPTY,
    CAPABILITY_WEB_SEARCH_ERROR,
    CAPABILITY_WEB_SEARCH_LOG_WRITE_FAILED,
)
from app.agent.state import AgentState
from app.domain.services.web_search import (
    WEB_SEARCH_CONFIG_REQUIRED,
    WEB_SEARCH_EMPTY,
    WEB_SEARCH_ERROR,
    WEB_SEARCH_LOG_WRITE_FAILED,
    WebSearchPort,
    WebSearchResult,
)
from app.agent.utils.think_utils import emit_think
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer


class WebSearchEntryNode:
    """执行一次由按钮触发的联网搜索。"""

    def __init__(self, search_port: WebSearchPort | None = None) -> None:
        self._search_port = search_port

    async def __call__(self, state: AgentState) -> dict:
        timer = Timer()
        requested = bool(state.get("web_search_requested"))
        if not requested:
            # 只要按钮没有开启，就绝不能调用远程 MCP；仍返回统一能力结果，
            # 让回答链可以给出“请先开启按钮”的明确 tag。
            emit_think("web_search_entry_node", "联网搜索未开启，请先点击「联网搜索」按钮")
            return {
                "capability_result": _capability(
                    status=CAPABILITY_DISABLED,
                    content="请先开启「联网搜索」按钮",
                    metadata={"reason": "web search was not requested by the UI"},
                ),
                "trace": [
                    make_trace(
                        "web_search_entry_node",
                        "success",
                        timer.elapsed_ms(),
                        extra={"requested": False, "status": CAPABILITY_DISABLED},
                    )
                ],
            }

        query = state.get("normalized_query") or state.get("question", "")
        if self._search_port is None:
            # 生产容器一定会注入端口；缺省实例用于单元测试/兼容直调，
            # 不访问网络也不抛出难以理解的 KeyError。
            result = None
        else:
            result = await self._search_port.search(
                query,
                conversation_id=state.get("conversation_id", ""),
            )

        if result is None:
            status = CAPABILITY_WEB_SEARCH_CONFIG_REQUIRED
            content = "需要配置 TAVILY_API_KEY"
            metadata = {"reason": "web search port is not configured"}
            evidence: list[dict] = []
        else:
            status = _capability_status(result.status)
            content = result.error or None
            metadata = {
                "search_id": result.search_id,
                "log_path": result.log_path,
                "duration_ms": result.duration_ms,
                "result_count": len(result.results),
                "query": query,
            }
            # 只有“成功且已落盘”的结果才能进入回答链；适配器在日志写入
            # 失败时会返回 LOG_WRITE_FAILED，即使内存里仍有结果，也必须
            # fail-closed，避免出现“已搜索但没有永久留档”的假成功。
            evidence = [
                {
                    "id": f"web:{result.search_id}:{index}",
                    "document_id": "",
                    "chunk_id": "",
                    "title": item.title,
                    "content": item.content,
                    "query": query,
                    "query_type": "web",
                    "source_name": item.title,
                    "source_type": "web",
                    "source_url": item.url,
                    "metadata": item.metadata,
                }
                for index, item in enumerate(result.results, start=1)
            ] if status == CAPABILITY_SUCCESS else []

        if status == CAPABILITY_WEB_SEARCH_CONFIG_REQUIRED:
            emit_think("web_search_entry_node", "联网搜索需要配置 TAVILY_API_KEY")
        elif status == CAPABILITY_WEB_SEARCH_EMPTY:
            emit_think("web_search_entry_node", "联网搜索完成，但没有可展示的网页结果")
        elif status in (CAPABILITY_WEB_SEARCH_ERROR, CAPABILITY_WEB_SEARCH_LOG_WRITE_FAILED):
            emit_think("web_search_entry_node", content or "联网搜索失败")
        else:
            emit_think("web_search_entry_node", f"联网搜索完成：找到 {len(evidence)} 条网页结果")

        return {
            "capability_result": {
                "capability": "web_search",
                "status": status,
                "content": content,
                "evidence": evidence,
                "citations": [],
                "metadata": metadata,
            },
            "trace": [
                make_trace(
                    "web_search_entry_node",
                    "success",
                    timer.elapsed_ms(),
                    extra={"requested": True, "status": status, "result_count": len(evidence)},
                )
            ],
        }


def _capability_status(status: str) -> str:
    """把领域端口状态映射为 Agent 常量，避免节点散落字符串。"""
    return {
        WEB_SEARCH_CONFIG_REQUIRED: CAPABILITY_WEB_SEARCH_CONFIG_REQUIRED,
        WEB_SEARCH_EMPTY: CAPABILITY_WEB_SEARCH_EMPTY,
        WEB_SEARCH_ERROR: CAPABILITY_WEB_SEARCH_ERROR,
        WEB_SEARCH_LOG_WRITE_FAILED: CAPABILITY_WEB_SEARCH_LOG_WRITE_FAILED,
    }.get(status, status)


def _capability(
    *,
    status: str,
    content: str | None,
    metadata: dict,
) -> dict:
    """构造按钮未开启等无远程结果的统一能力结构。"""
    return {
        "capability": "web_search",
        "status": status,
        "content": content,
        "evidence": [],
        "citations": [],
        "metadata": metadata,
    }
