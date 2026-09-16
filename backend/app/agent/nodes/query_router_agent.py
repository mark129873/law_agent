"""意图路由节点（BE-036，设计 §11.1）：规范化 + 意图识别 + 请求类型判断。"""

from __future__ import annotations

from app.agent.config import AgentConfig
from app.agent.prompts.query_router import build_router_messages
from app.agent.schemas import QueryRouterOutput
from app.agent.services.llm_service import LLMService
from app.agent.state import AgentState
from app.agent.utils.think_utils import emit_think
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer

# 请求类型 → 思考内容文案（BE-042/D9：JSON 结构化输出拼成中文句子后打印）
_REQUEST_TYPE_LABELS = {
    "local_rag": "法律事实型问题，将检索知识库",
    "plugin": "插件能力请求",
    "web": "网络搜索请求",
    "direct": "一般性对话，将直接回答",
}

# 关闭按钮时仍需识别“我想联网”的明确意图，才能在不触网的前提下
# 返回“请先开启按钮”的提示。这里使用高置信度的产品词，而不是把所有
# 法律问题都当成 Web 请求；真正的远程调用仍由 web_search_requested 守卫。
_WEB_SEARCH_HINTS = (
    "联网",
    "上网",
    "网页",
    "网上",
    "搜索",
    "搜一下",
    "查一下",
    "最新",
    "实时",
    "今日新闻",
    "latest",
    "search",
    "browse",
    "web search",
)


class QueryRouterAgent:
    """Query normalize / Intent classify / 请求类型判断 / 基础条件提取。

    不负责（设计 §11.1）：复杂 Retrieval Plan、SubQuery、RAG 策略生成
    ——那些是子图规划器的职责。
    """

    def __init__(self, llm: LLMService, config: AgentConfig) -> None:
        self._llm = llm
        self._config = config

    async def __call__(self, state: AgentState) -> dict:
        timer = Timer()
        question = state["question"]
        requested = bool(state.get("web_search_requested"))
        if requested:
            # 联网按钮是显式产品开关，不能让 LLM 把用户已经选择的能力
            # 改路到本地 RAG；同时跳过一次无必要的意图分类调用。
            routed = QueryRouterOutput(
                normalized_query=question,
                intent="web_request",
                request_type="web",
            )
            model_name = "explicit_ui_mode"
        else:
            if _looks_like_web_search(question):
                # 按钮关闭且问题明确要求网络信息时，仍走标准 QueryRouter →
                # Orchestrator → Web 节点路径；Web 节点会返回 DISABLED，
                # 因而只提示用户，不会调用 Tavily。
                routed = QueryRouterOutput(
                    normalized_query=question,
                    intent="web_request",
                    request_type="web",
                )
                model_name = "explicit_ui_guard"
            else:
                # 安全默认：解析失败 → 原问题透传 + 法律问题走检索（宁可多检索不可漏依据）
                default = QueryRouterOutput(normalized_query=question)
                routed = await self._llm.structured_invoke(
                    build_router_messages(question), QueryRouterOutput, default=default
                )
                model_name = self._llm.model_name
        # 思考内容（BE-042）：把结构化判读拼成一句中文，前端思考块可读
        emit_think(
            "query_router_agent",
            f"意图判定：{_REQUEST_TYPE_LABELS.get(routed.request_type, routed.request_type)}",
        )
        return {
            "original_query": question,
            "normalized_query": routed.normalized_query or question,
            "intent": routed.intent,
            "request_type": routed.request_type,
            "extracted_conditions": routed.extracted_conditions,
            # 该字段只描述请求是否由前端按钮触发，不来自全局配置。
            "web_search_requested": requested,
            "trace": [
                make_trace(
                    "query_router_agent",
                    "success",
                    timer.elapsed_ms(),
                    extra={
                        "model": model_name,
                        "intent": routed.intent,
                        "request_type": routed.request_type,
                    },
                )
            ],
        }


def _looks_like_web_search(question: str) -> bool:
    """判断用户是否明确提到网页/最新信息；仅用于关闭按钮时的提示路由。"""
    normalized = question.casefold()
    return any(hint.casefold() in normalized for hint in _WEB_SEARCH_HINTS)
