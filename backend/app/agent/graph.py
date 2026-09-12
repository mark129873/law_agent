"""LangGraph 问答工作流：建造者 + 端口适配器。

为什么这样拆分：
- `QaGraphBuilder`（建造者模式）负责把节点装配成图，装配规则集中一处；
- `LangGraphQaWorkflow`（适配器模式）显式实现 QaWorkflow 领域端口，
  把 langgraph 引擎封在适配器之内——引擎可替换而端口不变。

BE-030：统一 Plan-and-Execute 闭环，plan → retrieve? → generate → verify，
verify 据判定与预算条件回跳 plan / generate（见 ARCHITECTURE.md §5）。
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from app.agent.nodes import (
    MAX_PLAN_RUNS,
    VERDICT_CONTRACT,
    VERDICT_GROUNDING,
    GenerateNode,
    PlanNode,
    RetrieveNode,
    VerifyNode,
)
from app.agent.state import AgentState
from app.application.services.rag_service import RagService
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.services.qa_workflow import QaWorkflow

logger = logging.getLogger("app.agent.graph")


class QaGraphBuilder:
    """问答工作流建造者：统一规划闭环 + 条件回边。

    为什么所有问题都进规划节点：简单问题在规划器内退化为单子查询
    （透传原问法），与复杂问题共用同一拓扑——省去问题分类路由，
    也不存在"分类错误把复杂问题送进简单路径"的失效模式。

    rag 为 None 时（基础工作流）跳过 retrieve：规划仍然执行
    （对问答无害且保持单一拓扑心智模型），但没有任何 sources 事件。
    """

    def __init__(
        self,
        llm: LLMProvider,
        rag: RagService | None = None,
        planner: LLMProvider | None = None,
    ) -> None:
        self._llm = llm
        self._rag = rag
        # 规划器缺省用主 LLM：多数部署不单独配规划模型
        self._planner = planner or llm

    def build(self) -> CompiledStateGraph:
        builder = StateGraph(AgentState)
        builder.add_node("plan", PlanNode(self._planner))
        builder.add_edge(START, "plan")
        if self._rag is not None:
            builder.add_node("retrieve", RetrieveNode(self._rag))
            builder.add_node("generate", GenerateNode(self._llm))
            builder.add_node("verify", VerifyNode(self._llm))
            builder.add_edge("plan", "retrieve")
            builder.add_edge("generate", "verify")
            # 注意：retrieve 的出边只保留条件边——若同时保留静态边
            # retrieve→generate，条件边选 replan 时 generate 会在同一
            # 超级步并发执行，两个节点都写 verify_feedback 触发
            # InvalidUpdateError（并发写冲突）
            # 检索空命中（知识库无相关内容）→ 回规划改写子查询再试一轮；
            # 预算用尽时带空 context 进 generate，走 BE-017"信息不足"路径
            builder.add_conditional_edges(
                "retrieve",
                self._route_after_retrieve,
                {"replan": "plan", "generate": "generate"},
            )
            builder.add_conditional_edges(
                "verify",
                self._route_after_verify,
                {"replan": "plan", "regenerate": "generate", "end": END},
            )
        else:
            builder.add_node("generate", GenerateNode(self._llm))
            builder.add_node("verify", VerifyNode(self._llm))
            builder.add_edge("plan", "generate")
            builder.add_edge("generate", "verify")
            builder.add_conditional_edges(
                "verify",
                self._route_after_verify,
                {"replan": "plan", "regenerate": "generate", "end": END},
            )
        return builder.compile()

    @staticmethod
    def _route_after_retrieve(state: AgentState) -> str:
        """检索后路由：空命中且回规划预算未用尽 → 回规划，否则进生成。

        为什么条件边也要查预算：空命中打回与 verify 打回共用
        plan_runs 计数；预算用尽时带空 context 进 generate，
        走 BE-017"信息不足"路径，否则空知识库会无限重规划。
        """
        if not state.get("context", "").strip() and state.get("plan_runs", 0) < MAX_PLAN_RUNS:
            logger.info(
                "Agent retrieval empty, replanning",
                extra={"service": "agent", "plan_runs": state.get("plan_runs", 0)},
            )
            return "replan"
        return "generate"

    @staticmethod
    def _route_after_verify(state: AgentState) -> str:
        """校验后路由：按 verify 判定回跳或结束。

        预算检查在 VerifyNode 内完成——判定为 pass 时可能是真的
        通过，也可能是预算用尽降级放行，路由不需要重复判断。
        """
        verdict = state.get("verify_verdict", "pass")
        if verdict == VERDICT_GROUNDING:
            return "replan"
        if verdict == VERDICT_CONTRACT:
            return "regenerate"
        return "end"


class LangGraphQaWorkflow(QaWorkflow):
    """QaWorkflow 端口的 LangGraph 适配器（显式实现领域端口）。

    为什么显式继承协议：让"本类是端口的实现"成为类型系统事实，
    也让 issubclass/isinstance 校验在装配点可用。
    """

    def __init__(self, graph: CompiledStateGraph) -> None:
        self._graph = graph

    async def ainvoke(self, input: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return await self._graph.ainvoke(input, **kwargs)

    def astream(self, input: dict[str, Any], **kwargs: Any) -> AsyncIterator[Any]:
        return self._graph.astream(input, **kwargs)


def build_qa_graph(
    llm: LLMProvider,
    rag: RagService | None = None,
    planner: LLMProvider | None = None,
) -> CompiledStateGraph:
    """兼容入口：等价于 QaGraphBuilder(llm, rag, planner).build()（测试与脚本使用）。"""
    return QaGraphBuilder(llm, rag, planner).build()


async def run_qa(
    graph: CompiledStateGraph | QaWorkflow,
    question: str,
    history: list | None = None,
) -> str:
    """执行一次问答，返回模型回答（对上层隐藏图状态细节）。"""
    result = await graph.ainvoke({"question": question, "history": history or []})
    return result["answer"]
