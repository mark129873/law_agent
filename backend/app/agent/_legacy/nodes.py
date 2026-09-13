"""Agent 图节点（命令模式）。

为什么用类而不是闭包工厂：节点是有身份的业务组件（可独立测试、
可替换、可组合），`__call__` 让实例直接充当 LangGraph 节点，
抽象基类 `AgentNode` 固定节点契约，新增节点时继承即可（多态）。

BE-030 统一规划闭环：plan（拆解子查询）→ retrieve（多路检索合并）
→ generate（流式生成）→ verify（规则 + LLM judge 校验），
verify 可带着建议打回 plan 或 generate（受预算约束）。
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

from langgraph.config import get_stream_writer

from app.agent._legacy.prompts import (
    build_messages,
    build_plan_messages,
    build_verify_messages,
)
from app.agent._legacy.state import AgentState
from app.application.services.rag_service import RagService
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.services.qa_workflow import QaStreamEvent

logger = logging.getLogger("app.agent.nodes")

# 反馈环预算（BE-030）：各节点最多执行的总次数（含首次）。
# 为什么是硬编码常量而不是配置：预算是防死循环的正确性边界，
# 不是运行时可调参数；调整它属于行为变更，应走测试与文档流程。
MAX_PLAN_RUNS = 2
MAX_GENERATE_RUNS = 2

# verify 判定的三态（写进 verify_verdict，条件边据此路由）
VERDICT_PASS = "pass"
VERDICT_GROUNDING = "grounding"  # 依据不足：打回 plan 补检索
VERDICT_CONTRACT = "contract"  # 表达契约失败：打回 generate 重写


class AgentNode(ABC):
    """图节点基类：实现即命令（__call__ 使实例可直接注册为图节点）。"""

    @abstractmethod
    async def __call__(self, state: AgentState) -> dict:
        """处理工作流状态，返回本节点的状态增量。"""


def parse_sub_queries(raw: str, question: str, max_queries: int = 3) -> list[str]:
    """解析规划器输出为子查询列表（纯函数，便于单测）。

    为什么做容错回退：规划器是小模型，输出可能不是合法 JSON
    （带解释、markdown 代码块、截断等）。规划是增强而非闸门——
    解析失败时透传原问题，问答流程永远可以继续。
    """
    text = raw.strip()
    # 容忍模型把 JSON 包在 ```json ... ``` 代码块里
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return [question]
    # 只接受"字符串数组"这一种合法形态
    if not isinstance(data, list) or not all(isinstance(q, str) for q in data):
        return [question]
    queries = [q.strip() for q in data if q.strip()]
    if not queries:
        return [question]
    # 子查询数超上限时截断：规划器失控输出十几条时保护检索成本
    return queries[:max_queries]


def parse_judge_verdict(raw: str) -> dict | None:
    """解析判分器输出为 verdict 结构（纯函数）。

    返回 None 表示输出不可解析——调用方将其视为 pass
    （判分是增强而非闸门，见 ARCHITECTURE.md §5）。
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    verdict = data.get("verdict")
    if verdict not in (VERDICT_PASS, VERDICT_GROUNDING, VERDICT_CONTRACT):
        return None
    return {
        "verdict": verdict,
        "feedback": str(data.get("feedback", "")),
        "unsupported": [str(u) for u in data.get("unsupported", []) if u],
    }


class PlanNode(AgentNode):
    """规划节点：把用户问题拆解为知识库检索子查询（BE-030）。

    为什么规划独立成节点：多主题法律问题一次 top_k 检索通常只
    命中部分主题，先拆解再逐条检索能显著提高依据覆盖率；
    同时 verify 打回的"依据不足"建议也在此入口回流（重规划）。
    """

    def __init__(self, planner: LLMProvider) -> None:
        self._planner = planner

    async def __call__(self, state: AgentState) -> dict:
        runs = state.get("plan_runs", 0) + 1
        feedback = state.get("verify_feedback", "")
        messages = build_plan_messages(state["question"], feedback=feedback)
        logger.info(
            "Agent plan started",
            extra={
                "service": "agent",
                "model": self._planner.model_name,
                "plan_runs": runs,
                "has_feedback": bool(feedback),
            },
        )
        # 规划用非流式 chat()：子查询列表是整体 JSON，流式无意义
        raw = await self._planner.chat(messages)
        sub_queries = parse_sub_queries(raw, state["question"])
        logger.info(
            "Agent plan completed",
            extra={"service": "agent", "sub_query_count": len(sub_queries)},
        )
        # 推 plan 事件：重规划时也推，前端据此更新拆解展示
        get_stream_writer()(
            QaStreamEvent(type="plan", sub_queries=tuple(sub_queries))
        )
        return {
            "sub_queries": sub_queries,
            "plan_runs": runs,
            # 消费掉反馈：打回建议只作用于本轮规划，避免残留影响后续轮次
            "verify_feedback": "",
        }


class RetrieveNode(AgentNode):
    """检索节点：逐子查询混合检索并合并，推送参考来源事件。

    为什么在此推送 sources 事件：检索命中的 chunk 是"参考文档"展示的
    唯一事实来源（FE-011），在检索发生地推送保证 Prompt 依据与前端
    展示天然同源，不会出现"回答引用了 A、参考面板却是 B"的漂移。
    重规划后本节点会再次执行并再次推送 sources——
    服务层与前端都以最新一批为准（ARCHITECTURE.md §7）。
    """

    def __init__(self, rag: RagService) -> None:
        self._rag = rag

    async def __call__(self, state: AgentState) -> dict:
        sub_queries = state.get("sub_queries") or [state["question"]]
        chunks = await self._rag.retrieve_queries(sub_queries)
        context = self._rag.format_context(chunks)
        if chunks:
            sources = tuple(
                {
                    "source": chunk.chunk.metadata.get("filename", "未知来源"),
                    "content": chunk.chunk.content,
                }
                for chunk in chunks
            )
            # astream(stream_mode="custom") 时事件推送给调用方；ainvoke 时被忽略
            get_stream_writer()(QaStreamEvent(type="sources", sources=sources))
        return {"context": context}


class GenerateNode(AgentNode):
    """生成节点：组装 Prompt 并经 LLMProvider 流式生成回答。

    为什么在节点内通过 stream writer 推送 token：流式（astream + custom）
    与非流式（ainvoke）执行同一个节点实例，Prompt 组装与检索逻辑
    只有一份实现；非流式调用时 writer 事件无人消费，行为不变。
    """

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def __call__(self, state: AgentState) -> dict:
        runs = state.get("generate_runs", 0) + 1
        feedback = state.get("verify_feedback", "")
        messages = build_messages(
            question=state["question"],
            context=state.get("context", ""),
            history=state.get("history"),
            feedback=feedback,
        )
        logger.info(
            "Agent generate started",
            extra={
                "service": "agent",
                "model": self._llm.model_name,
                "message_count": len(messages),
                "generate_runs": runs,
                "has_feedback": bool(feedback),
            },
        )
        writer = get_stream_writer()
        collected: list[str] = []
        async for chunk in self._llm.stream(messages):
            collected.append(chunk)
            # 统一以领域事件推送（与 RetrieveNode 的 sources 事件同构），
            # 消费方按 event.type 分流，不再猜测裸字符串含义
            writer(QaStreamEvent(type="delta", content=chunk))
        answer = "".join(collected)
        logger.info(
            "Agent generate completed",
            extra={"service": "agent", "model": self._llm.model_name, "answer_length": len(answer)},
        )
        return {
            "answer": answer,
            "history": messages,
            "generate_runs": runs,
            "verify_feedback": "",
        }


class VerifyNode(AgentNode):
    """校验节点：规则档 + LLM judge 档，判定是否打回（BE-030）。

    为什么规则档先行：引用来源存在性、信息不足声明等契约是确定性
    检查，零 LLM 成本且不会误判；judge 只处理需要语义理解的
    groundedness 问题（结论是否真的有出处）。

    为什么判分解析失败视为 pass：判分是增强而非闸门——判分器
    （小模型）自身输出不可靠时，不能让问答被卡死；
    预算用尽同样直接放行，避免反馈环死循环。
    """

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def __call__(self, state: AgentState) -> dict:
        answer = state.get("answer", "")
        context = state.get("context", "")

        # ---- 规则档（确定性契约检查，零成本）----
        contract_error = ""
        if context:
            # 有依据时回答必须注明来源（Prompt 中的【来源：xxx】格式）
            if "【来源：" not in answer:
                contract_error = "回答引用了参考依据但未注明来源文件"
        else:
            # 无依据时必须按 BE-017 契约声明信息不足
            if "知识库中暂无相关依据" not in answer:
                contract_error = "参考依据为空但回答未声明信息不足，禁止编造"
        if not answer.strip():
            contract_error = contract_error or "回答为空"

        if contract_error:
            return self._route_back(state, VERDICT_CONTRACT, contract_error)

        # ---- LLM judge 档（groundedness 语义校验）----
        messages = build_verify_messages(state["question"], context, answer)
        raw = await self._llm.chat(messages)
        report = parse_judge_verdict(raw)
        if report is None:
            logger.warning(
                "Agent judge output unparsable, treated as pass",
                extra={"service": "agent", "raw_length": len(raw)},
            )
            return {"verify_verdict": VERDICT_PASS, "verify_feedback": ""}

        if report["verdict"] == VERDICT_GROUNDING:
            # 把无依据结论清单组装成规划器能消费的建议
            unsupported = "；".join(report["unsupported"])
            feedback = report["feedback"]
            if unsupported:
                feedback = f"{feedback}（无依据结论：{unsupported}）"
            return self._route_back(state, VERDICT_GROUNDING, feedback or "回答存在无依据的结论")
        if report["verdict"] == VERDICT_CONTRACT:
            return self._route_back(state, VERDICT_CONTRACT, report["feedback"])

        return {"verify_verdict": VERDICT_PASS, "verify_feedback": ""}

    def _route_back(self, state: AgentState, verdict: str, feedback: str) -> dict:
        """构造打回的状态增量；预算用尽时降级为放行并记 WARN。

        为什么预算判定放在节点内而不是条件边：regenerating 事件
        与"是否真的打回"必须一致——节点在打回前推事件、写判定，
        条件边只读判定路由，两处逻辑不会漂移。
        """
        grounding = verdict == VERDICT_GROUNDING
        budget_left = (
            state.get("plan_runs", 0) < MAX_PLAN_RUNS
            if grounding
            else state.get("generate_runs", 0) < MAX_GENERATE_RUNS
        )
        if not budget_left:
            logger.warning(
                "Agent verify failed but budget exhausted, passing current answer",
                extra={"service": "agent", "verdict": verdict, "feedback": feedback},
            )
            return {"verify_verdict": VERDICT_PASS, "verify_feedback": ""}

        logger.info(
            "Agent verify rejected answer, routing back",
            extra={"service": "agent", "verdict": verdict, "feedback": feedback},
        )
        get_stream_writer()(QaStreamEvent(type="regenerating"))
        return {"verify_verdict": verdict, "verify_feedback": feedback}
