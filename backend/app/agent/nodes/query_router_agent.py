"""意图路由节点（BE-036，设计 §11.1）：规范化 + 意图识别 + 请求类型判断。"""

from __future__ import annotations

from app.agent.config import AgentConfig
from app.agent.prompts.query_router import build_router_messages
from app.agent.schemas import QueryRouterOutput
from app.agent.services.llm_service import LLMService
from app.agent.state import AgentState
from app.agent.utils.trace_utils import make_trace
from app.agent.utils.timing_utils import Timer


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
        # 安全默认：解析失败 → 原问题透传 + 法律问题走检索（宁可多检索不可漏依据）
        default = QueryRouterOutput(normalized_query=question)
        routed = await self._llm.structured_invoke(
            build_router_messages(question), QueryRouterOutput, default=default
        )
        return {
            "original_query": question,
            "normalized_query": routed.normalized_query or question,
            "intent": routed.intent,
            "request_type": routed.request_type,
            "extracted_conditions": routed.extracted_conditions,
            # Web Search 开关由配置注入（一期 Stub：默认 False → DISABLED）
            "web_search_enabled": self._config.web_search_enabled_default,
            "trace": [
                make_trace(
                    "query_router_agent",
                    "success",
                    timer.elapsed_ms(),
                    extra={
                        "model": self._llm.model_name,
                        "intent": routed.intent,
                        "request_type": routed.request_type,
                    },
                )
            ],
        }
