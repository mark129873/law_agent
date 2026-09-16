"""主图组装：建造者 + 端口适配器（BE-038，设计 §3/§44）。

为什么这样拆分：
- `AgentGraphBuilder`（建造者模式）按设计 §3 拓扑装配主图，
  Local Legal RAG 子图作为编译图节点整体接入（约束 5），
  装配规则集中一处；
- `LangGraphQaWorkflow`（适配器模式）显式实现 QaWorkflow 领域端口，
  langgraph 引擎封在适配器之内（对外契约不随重写变化）。

SSE 事件在节点内推送（单一事实来源）：plan=hybrid_retriever 检索策略、
sources=rag_result 本地证据、web_sources=联网网页预览、delta=回答流式、
regenerating=重生成前提示。
"""

from __future__ import annotations

import asyncio
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.config import AgentConfig
from app.agent.events import event_emitter_var
from app.agent.node_status import add_node_traced
from app.agent.nodes import (
    ACTION_TARGETS,
    ActionRouterNode,
    AnswerGeneratorAgent,
    DirectAnswerAgent,
    FinalAnswerNode,
    GroundingCheckerAgent,
    ObservationNode,
    OrchestratorAgent,
    QueryRouterAgent,
    route_action,
)
from app.agent.services.citation_service import CitationService
from app.agent.services.llm_service import LLMService
from app.agent.services.milvus_service import MilvusService
from app.agent.services.reranker_service import RerankerService
from app.agent.state import AgentState
from app.agent.subgraphs.legal_rag.config import LegalRAGConfig
from app.agent.subgraphs.legal_rag.graph import build_legal_rag_graph
from app.agent.plugins import PluginEntryNode, PluginStubNode
from app.agent.utils.think_utils import emit_think
from app.agent.web import WebSearchEntryNode
from app.domain.services.web_search import WebSearchPort
from app.domain.services.qa_workflow import QaWorkflow

# legal_rag 子图回写主图的键（其余子图内部键不外泄，见 LegalRAGState）
_RAG_OUTPUT_KEYS = (
    "rag_status",
    "ranked_evidence",
    "missing_evidence",
    "suggested_external_queries",
)


class AgentGraphBuilder:
    """主图建造者：顶层编排循环 + Capability 分派 + 回答收尾链（设计 §3）。

    模型分工：planner 服务决策密集的轻节点（意图路由/编排/RAG 子图规划），
    主 LLM 服务回答与校验（流式生成）——PLANNER_PROVIDER 可为强模型，
    与 BE-030 的"强模型规划 + 快模型执行"组合一脉相承。
    """

    def __init__(
        self,
        llm: LLMService,
        planner: LLMService,
        milvus: MilvusService,
        reranker: RerankerService,
        agent_config: AgentConfig | None = None,
        rag_config: LegalRAGConfig | None = None,
        web_search: WebSearchPort | None = None,
    ) -> None:
        self._llm = llm
        self._planner = planner
        self._milvus = milvus
        self._reranker = reranker
        self._agent_config = agent_config or AgentConfig()
        self._rag_config = rag_config or LegalRAGConfig()
        self._web_search = web_search

    def _make_rag_node(self):
        """构造 legal_rag 子图调用节点：显式输入/输出过滤（BE-038/041）。"""
        rag_graph = build_legal_rag_graph(
            self._planner, self._milvus, self._reranker, self._rag_config
        )

        async def _run_legal_rag(state: AgentState) -> dict:
            result = await rag_graph.ainvoke(
                {
                    "original_query": state.get("original_query") or state.get("question", ""),
                    "normalized_query": state.get("normalized_query", ""),
                }
            )
            return {key: result[key] for key in _RAG_OUTPUT_KEYS if key in result}

        return _run_legal_rag

    def build(self) -> CompiledStateGraph:
        builder = StateGraph(AgentState)

        # 全部节点经 with_node_status 包装（BE-041）：起止 status 事件 + 日志
        add_node_traced(builder, "query_router_agent", QueryRouterAgent(self._planner, self._agent_config))
        add_node_traced(builder, "orchestrator_agent", OrchestratorAgent(self._planner, self._agent_config))
        add_node_traced(builder, "action_router_node", ActionRouterNode())
        # Local Legal RAG 子图（约束 5）：显式包装子图调用——输入只传检索
        # 所需键，输出只回写主图声明的键（比依赖 langgraph 同名通道匹配
        # 更确定，也使子图复合节点本身获得 status 事件）
        add_node_traced(builder, "legal_rag_subgraph", self._make_rag_node())
        add_node_traced(builder, "plugin_entry_node", PluginEntryNode())
        add_node_traced(builder, "plugin_stub_node", PluginStubNode())
        add_node_traced(builder, "web_search_entry_node", WebSearchEntryNode(self._web_search))
        add_node_traced(builder, "observation_node", ObservationNode())
        add_node_traced(builder, "direct_answer_agent", DirectAnswerAgent(self._llm))
        add_node_traced(builder, "answer_generator_agent", AnswerGeneratorAgent(self._llm))
        add_node_traced(builder, "grounding_checker_agent", GroundingCheckerAgent(self._llm))
        add_node_traced(builder, "final_answer_node", FinalAnswerNode(CitationService()))

        # ---- 入口与顶层循环（设计 §3）----
        builder.add_edge(START, "query_router_agent")
        builder.add_edge("query_router_agent", "orchestrator_agent")
        builder.add_edge("orchestrator_agent", "action_router_node")
        # Capability 分派（设计 §46.1 映射表）
        builder.add_conditional_edges(
            "action_router_node", route_action, list(ACTION_TARGETS.values())
        )
        # 各 Capability → observation → 回编排（受 max_global_steps 预算）
        builder.add_edge("legal_rag_subgraph", "observation_node")
        builder.add_edge("web_search_entry_node", "observation_node")
        builder.add_edge("plugin_entry_node", "plugin_stub_node")
        builder.add_edge("plugin_stub_node", "observation_node")
        builder.add_edge("direct_answer_agent", "observation_node")
        builder.add_edge("observation_node", "orchestrator_agent")

        # ---- 回答收尾链（finish 后唯一路径）----
        builder.add_edge("answer_generator_agent", "grounding_checker_agent")
        builder.add_conditional_edges(
            "grounding_checker_agent",
            route_after_grounding(self._agent_config),
            {"retry": "orchestrator_agent", "final": "final_answer_node"},
        )
        builder.add_edge("final_answer_node", END)
        return builder.compile()


def route_after_grounding(config: AgentConfig):
    """grounding 后路由（设计 §3）：通过 → 收尾；未过且预算内 → 回编排；
    预算耗尽 → 直接进入确定性收尾（预算检查在条件边）。

    为什么预算比较用 >= 而不是 >：grounding_checker_agent 每次执行
    都会 +1 计数（含本次），即"本次校验已经消耗了一个步数"。
    预算耗尽时不再额外调用 LLM，避免低质量兜底回答覆盖已有草稿。
    """
    def _route(state: AgentState) -> str:
        if state.get("grounding_passed"):
            return "final"
        if int(state.get("global_step_count") or 0) < config.max_global_steps:
            return "retry"
        # 路由没有独立节点，因此用 grounding 标签记录确定性收尾原因，
        # 让前端思考块仍能解释为何没有继续重试。
        emit_think("grounding_checker_agent", "依据校验未通过且重试预算耗尽，直接收尾当前回答")
        return "final"

    return _route


class LangGraphQaWorkflow(QaWorkflow):
    """QaWorkflow 端口的 LangGraph 适配器（显式实现领域端口）。

    为什么 astream 用事件队列而不是 graph.astream(custom)：实测
    langgraph 1.2.11 子图节点的 custom 事件不上浮父图流，而 plan/
    sources 事件产自 legal_rag 子图内部（见 app/agent/events.py）。
    适配器在执行期间经 ContextVar 注入队列接收器：节点 emit_event
    → 队列 → 本生成器逐事件产出——执行顺序即事件顺序，与图引擎
    解耦；ainvoke 路径无接收器，事件自动丢弃。
    """

    def __init__(self, graph: CompiledStateGraph) -> None:
        self._graph = graph

    async def ainvoke(self, input: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return await self._graph.ainvoke(input, **kwargs)

    async def astream(self, input: dict[str, Any], **kwargs: Any):
        queue: asyncio.Queue = asyncio.Queue()
        token = event_emitter_var.set(queue.put_nowait)
        task = asyncio.create_task(self._run_to_end(input, queue, kwargs))
        try:
            while True:
                event = await queue.get()
                if event is None:  # 结束哨兵（_run_to_end 的 finally 必达）
                    break
                yield event
            # 图执行异常在此处重新抛出（ChatService 捕获并记日志）
            await task
        except GeneratorExit:
            # 消费方提前关闭（客户端断开）：取消图执行，避免任务泄漏
            task.cancel()
            raise
        finally:
            event_emitter_var.reset(token)

    async def _run_to_end(self, input: dict[str, Any], queue: asyncio.Queue, kwargs: dict) -> None:
        try:
            await self._graph.ainvoke(input, **kwargs)
        finally:
            queue.put_nowait(None)
