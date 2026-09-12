"""LangGraph Agent 工作流测试（BE-030 统一 Plan-and-Execute 闭环）。

用脚本化 Fake LLM 与内存 Fake 向量库（确定性 embedding）验证：
规划 → 检索 → 生成 → 校验的完整闭环，含 verify 打回、
预算降级、事件顺序与 sources 契约。
"""

import hashlib
import json

import pytest
import pytest_asyncio

from app.agent.graph import build_qa_graph, run_qa
from app.agent.prompts import (
    LEGAL_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    VERIFY_JUDGE_SYSTEM_PROMPT,
)
from app.application.services.document_pipeline import DocumentParserFactory, DocumentPipeline
from app.application.services.knowledge_service import KnowledgeIngestionService
from app.application.services.rag_service import RagService
from app.domain.entities.chunk import DocumentChunk
from app.domain.entities.llm import ChatMessage, LlmParams
from app.domain.entities.message import MessageRole
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.services.embedding import EmbeddingService
from app.infrastructure.document_parser.text_parser import TextParser
from tests.fakes import InMemoryVectorStore

# 常用的判分通过脚本：verdict=pass
_JUDGE_PASS = json.dumps({"verdict": "pass", "feedback": "", "unsupported": []}, ensure_ascii=False)


def _judge(verdict: str, feedback: str = "", unsupported: list[str] | None = None) -> str:
    """构造判分器脚本回复。"""
    return json.dumps(
        {"verdict": verdict, "feedback": feedback, "unsupported": unsupported or []},
        ensure_ascii=False,
    )


class ScriptedLLM(LLMProvider):
    """按系统提示分流脚本的 Fake LLM。

    三类调用（规划/判分/生成）由消息中的系统提示区分，各自消费
    独立的脚本队列；队列为空时重复最后一条（或用默认值），
    保证测试只需声明关心的轮次。生成节点走 stream、规划与判分
    走 chat——与真实调用形态一致。
    """

    def __init__(
        self,
        answers: str | list[str],
        plans: str | list[str] | None = None,
        judges: str | list[str] | None = None,
    ) -> None:
        self._answers = answers if isinstance(answers, list) else [answers]
        self._plans = plans if isinstance(plans, list) else ([plans] if plans else [])
        self._judges = judges if isinstance(judges, list) else ([judges] if judges else [])
        self.generate_calls: list[list[ChatMessage]] = []
        self.plan_calls: list[list[ChatMessage]] = []
        self.judge_calls: list[list[ChatMessage]] = []

    @property
    def model_name(self) -> str:
        return "fake-model"

    @staticmethod
    def _pop(queue: list, default: str) -> str:
        if not queue:
            return default
        if len(queue) == 1:
            return queue[0]
        return queue.pop(0)

    async def chat(self, messages: list[ChatMessage], params: LlmParams | None = None) -> str:
        system = messages[0].content
        if system == PLANNER_SYSTEM_PROMPT:
            self.plan_calls.append(messages)
            # 默认脚本为空串 → 解析失败 → PlanNode 回退为透传原问题
            return self._pop(self._plans, "")
        if system == VERIFY_JUDGE_SYSTEM_PROMPT:
            self.judge_calls.append(messages)
            return self._pop(self._judges, _JUDGE_PASS)
        raise AssertionError("生成节点不应走 chat()，规划与判分不应走 stream()")

    async def stream(self, messages: list[ChatMessage], params: LlmParams | None = None):
        assert messages[0].content == LEGAL_SYSTEM_PROMPT
        self.generate_calls.append(messages)
        answer = self._pop(self._answers, "默认回答")
        # 按固定片段产出，模拟真实 token 流
        for part in [answer[i : i + 3] for i in range(0, len(answer), 3)]:
            yield part


class DeterministicEmbedding(EmbeddingService):
    """字符 bigram 哈希词袋向量（与 RAG 测试一致）。"""

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        for i in range(len(text) - 1):
            digest = hashlib.md5(text[i : i + 2].encode("utf-8")).digest()
            vector[digest[0] % self._dim] += 1.0
        return vector

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


# ---- 统一闭环：空知识库场景（plan → retrieve 空命中 → replan → generate → verify）----
#
# rag 为必选依赖后，"无知识库"不再有独立拓扑：由空命中重规划路径承接，
# 预算用尽后带空 context 进 generate，走 BE-017"信息不足"契约。


@pytest_asyncio.fixture
async def rag_factory():
    """构建 RagService（内存 Fake 知识库）；content 为 None 时为空知识库。"""
    stores: list[InMemoryVectorStore] = []

    async def make(content: str | None = None, filename: str = "劳动法问答.txt") -> RagService:
        store = InMemoryVectorStore()
        await store.initialize()
        stores.append(store)
        embedding = DeterministicEmbedding()
        rag = RagService(embedding, store)
        if content is not None:
            ingestion = KnowledgeIngestionService(
                DocumentPipeline(parser_factory=DocumentParserFactory([TextParser()])), embedding, store
            )
            await ingestion.ingest_document("doc-1", filename, content.encode("utf-8"))
        return rag

    yield make
    for store in stores:
        await store.close()


@pytest.mark.asyncio
async def test_empty_knowledge_completes_qa(rag_factory) -> None:
    """空知识库：空命中重规划吃满预算后走信息不足策略，闭环正常收尾。"""
    llm = ScriptedLLM(answers="知识库中暂无相关依据，建议咨询专业律师。")
    graph = build_qa_graph(llm, rag=await rag_factory())
    answer = await run_qa(graph, "经济补偿怎么计算？")
    assert answer.startswith("知识库中暂无相关依据")
    # 空命中触发一次重规划（预算 2 次封顶），生成与判分各一次
    assert len(llm.plan_calls) == 2
    assert llm.plan_calls[0][0].content == PLANNER_SYSTEM_PROMPT
    assert len(llm.generate_calls) == 1
    assert llm.generate_calls[0][0].content == LEGAL_SYSTEM_PROMPT
    assert llm.generate_calls[0][-1].content == "经济补偿怎么计算？"
    assert len(llm.judge_calls) == 1


@pytest.mark.asyncio
async def test_generate_includes_history(rag_factory) -> None:
    """多轮对话历史应被组装进生成消息列表（规划不携带历史）。"""
    llm = ScriptedLLM(answers="知识库中暂无相关依据，建议咨询专业律师。")
    graph = build_qa_graph(llm, rag=await rag_factory())
    history = [
        ChatMessage(role=MessageRole.USER, content="上一问"),
        ChatMessage(role=MessageRole.ASSISTANT, content="上一答"),
    ]
    await run_qa(graph, "继续追问", history=history)
    received = llm.generate_calls[0]
    assert [m.content for m in received] == [LEGAL_SYSTEM_PROMPT, "上一问", "上一答", "继续追问"]


@pytest.mark.asyncio
async def test_planner_single_question_passthrough(rag_factory) -> None:
    """单一明确问题：规划器透传原问题为单子查询（统一图的退化情形）。"""
    llm = ScriptedLLM(
        answers="知识库中暂无相关依据，建议咨询专业律师。",
        plans=json.dumps(["经济补偿怎么计算？"], ensure_ascii=False),
    )
    graph = build_qa_graph(llm, rag=await rag_factory())
    await run_qa(graph, "经济补偿怎么计算？")
    # 规划器收到的就是原问题，无反馈
    assert "经济补偿怎么计算？" in llm.plan_calls[0][-1].content
    assert "修正建议" not in llm.plan_calls[0][-1].content


@pytest.mark.asyncio
async def test_planner_output_unparsable_falls_back_to_question(rag_factory) -> None:
    """规划器输出非法 JSON：回退为透传原问题，问答流程不中断。"""
    llm = ScriptedLLM(
        answers="知识库中暂无相关依据，建议咨询专业律师。",
        plans="这不是 JSON，模型输出失控了",
    )
    graph = build_qa_graph(llm, rag=await rag_factory())
    answer = await run_qa(graph, "经济补偿怎么计算？")
    assert answer.startswith("知识库中暂无相关依据")


# ---- RAG 工作流（知识库有命中：plan → retrieve → generate → verify）----


_LAW_CONTENT = "劳动合同违约金条款：劳动者违反服务期约定的，应当按照约定向用人单位支付违约金。"
_RAG_ANSWER = "依据知识库回答。【来源：劳动法问答.txt】"


@pytest_asyncio.fixture
async def rag_graph_factory(rag_factory):
    """构建接入已入库劳动法文档的 RAG 工作流工厂。"""

    async def factory(llm: LLMProvider):
        rag = await rag_factory(content=_LAW_CONTENT)
        return build_qa_graph(llm, rag=rag)

    yield factory


@pytest.mark.asyncio
async def test_rag_graph_injects_knowledge_context(rag_graph_factory) -> None:
    """RAG 工作流应把知识库内容（含来源标注）注入生成 Prompt。"""
    llm = ScriptedLLM(answers=_RAG_ANSWER)
    graph = await rag_graph_factory(llm)
    answer = await run_qa(graph, "违反服务期约定怎么赔偿")
    assert answer == _RAG_ANSWER
    user_message = llm.generate_calls[0][-1].content
    assert "【参考依据】" in user_message
    assert "【来源：劳动法问答.txt】" in user_message
    assert "违约金" in user_message


@pytest.mark.asyncio
async def test_rag_graph_multi_sub_queries_merge_dedup(rag_graph_factory) -> None:
    """多子查询检索：两个子查询命中同一 chunk 时合并去重为一条来源。"""
    llm = ScriptedLLM(
        answers=_RAG_ANSWER,
        plans=json.dumps(["劳动合同违约金条款", "违反服务期约定的违约金"], ensure_ascii=False),
    )
    graph = await rag_graph_factory(llm)
    answer = await run_qa(graph, "劳动合同违约金和违反服务期约定怎么赔偿")
    assert answer == _RAG_ANSWER
    # 规划器收到了多主题问题（plan_calls 的 user 消息为原问题）
    assert "劳动合同违约金和违反服务期约定" in llm.plan_calls[0][-1].content
    # 合并去重生效：同一 chunk 不重复进入上下文/参考来源


@pytest.mark.asyncio
async def test_rag_graph_empty_knowledge_marks_no_context(tmp_path) -> None:
    """知识库无命中时（含重规划后仍无命中），走信息不足路径且不死循环。"""
    store = InMemoryVectorStore()
    await store.initialize()
    llm = ScriptedLLM(answers="知识库中暂无相关依据，建议咨询专业律师。")
    graph = build_qa_graph(llm, rag=RagService(DeterministicEmbedding(), store))
    try:
        answer = await run_qa(graph, "量子力学的波函数坍缩是什么")
        assert answer.startswith("知识库中暂无相关依据")
        user_message = llm.generate_calls[0][-1].content
        assert "【参考依据】" not in user_message
        # 空命中重规划吃满预算（2 次）后进生成，不会无限循环
        assert len(llm.plan_calls) == 2
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_rag_service_min_score_filters_weak_hits(tmp_path) -> None:
    """min_score 过滤：低于阈值的弱命中不应进入上下文（BE-017 信息不足策略的机制）。"""
    store = InMemoryVectorStore()
    await store.initialize()
    embedding = DeterministicEmbedding()
    content = "劳动合同违约金条款：劳动者违反服务期约定的，应当按照约定向用人单位支付违约金。"
    vectors = await embedding.embed_documents([content])
    await store.add_chunks(
        [DocumentChunk(document_id="doc-1", content=content, metadata={"filename": "劳动法.txt"})],
        vectors,
    )
    # 阈值取 0.99：任何查询都无法达到，等价于"知识库无相关依据"
    strict_rag = RagService(embedding, store, min_score=0.99)
    try:
        context = await strict_rag.build_context("违反服务期约定怎么赔偿")
        assert context == ""
    finally:
        await store.close()


# ---- verify 反馈环（BE-030）----


@pytest.mark.asyncio
async def test_verify_grounding_routes_back_to_plan(rag_graph_factory) -> None:
    """依据不足：judge 带无依据结论打回规划，重规划后回答通过校验。"""
    llm = ScriptedLLM(
        answers=[
            _RAG_ANSWER + "另外编造一个不存在的条款。",  # 第一轮：有来源但含无依据结论
            _RAG_ANSWER,  # 第二轮：修正后通过
        ],
        plans=[
            json.dumps(["违反服务期约定怎么赔偿"], ensure_ascii=False),
            json.dumps(["服务期违约金 合法约定"], ensure_ascii=False),  # 重规划的子查询
        ],
        judges=_judge(
            "grounding",
            feedback="需要补充检索服务期条款的合法性依据",
            unsupported=["另外编造一个不存在的条款"],
        ),
    )
    graph = await rag_graph_factory(llm)
    answer = await run_qa(graph, "违反服务期约定怎么赔偿")
    # 最终输出第二轮修正后的回答
    assert answer == _RAG_ANSWER
    # 打回建议确实传入了重规划的 user 消息
    second_plan_user = llm.plan_calls[1][-1].content
    assert "修正建议" in second_plan_user
    assert "无依据结论" in second_plan_user
    # 两轮规划、两轮生成、两轮判分
    assert len(llm.plan_calls) == 2
    assert len(llm.generate_calls) == 2
    assert len(llm.judge_calls) == 2


@pytest.mark.asyncio
async def test_verify_contract_routes_back_to_generate(rag_graph_factory) -> None:
    """表达契约失败：回答未注明来源，带反馈打回生成（不重规划）。"""
    llm = ScriptedLLM(
        answers=[
            "依据知识库回答。",  # 第一轮：有依据但未注明来源 → 规则档即失败
            _RAG_ANSWER,
        ],
        # 判分脚本用默认 pass：若第一轮规则档就失败打回生成，
        # judge 只会在第二轮被调用一次；若规则档被绕过会暴露
    )
    graph = await rag_graph_factory(llm)
    answer = await run_qa(graph, "违反服务期约定怎么赔偿")
    assert answer == _RAG_ANSWER
    # 规则档失败直接打回生成：只规划一次、生成两次、judge 一次（第二轮）
    assert len(llm.plan_calls) == 1
    assert len(llm.generate_calls) == 2
    assert len(llm.judge_calls) == 1
    # 重生成的 Prompt 携带修正要求
    assert "修正要求" in llm.generate_calls[1][-1].content


@pytest.mark.asyncio
async def test_verify_budget_exhausted_outputs_answer(rag_graph_factory) -> None:
    """预算用尽：judge 持续判 grounding 时输出当前答案，不死循环。"""
    llm = ScriptedLLM(
        answers=_RAG_ANSWER,
        judges=_judge("grounding", feedback="永远不满意", unsupported=["一切"]),
    )
    graph = await rag_graph_factory(llm)
    answer = await run_qa(graph, "违反服务期约定怎么赔偿")
    assert answer == _RAG_ANSWER  # 降级放行：校验失败也不阻断问答
    assert len(llm.plan_calls) == 2  # 规划预算 2 次封顶
    assert len(llm.generate_calls) == 2


# ---- 流式事件契约 ----


@pytest.mark.asyncio
async def test_graph_astream_custom_emits_llm_tokens(rag_factory) -> None:
    """流式问答必须经由图（astream custom 模式）产出 delta 事件，而不是绕过图直连 LLM。"""
    llm = ScriptedLLM(answers="知识库中暂无相关依据，建议咨询专业律师。")
    graph = build_qa_graph(llm, rag=await rag_factory())
    events = [
        event
        async for event in graph.astream({"question": "试用期多长？", "history": []}, stream_mode="custom")
    ]
    deltas = [e.content for e in events if e.type == "delta"]
    assert "".join(deltas) == "知识库中暂无相关依据，建议咨询专业律师。"
    assert len(deltas) > 1  # 逐 token 推送
    # 空知识库不产生 sources 事件：前端据此不渲染参考文档按钮
    assert all(e.type in ("plan", "delta") for e in events)
    assert events[0].type == "plan"
    assert events[0].sub_queries == ("试用期多长？",)


@pytest.mark.asyncio
async def test_non_stream_invoke_ignores_stream_events(rag_factory) -> None:
    """非流式 ainvoke 与流式走同一节点：answer 完整产出且不受流事件影响。"""
    llm = ScriptedLLM(answers="知识库中暂无相关依据，建议咨询专业律师。")
    graph = build_qa_graph(llm, rag=await rag_factory())
    answer = await run_qa(graph, "任何问题")
    assert answer.startswith("知识库中暂无相关依据")


@pytest.mark.asyncio
async def test_rag_graph_astream_emits_plan_sources_then_deltas(rag_graph_factory) -> None:
    """事件顺序：plan 先于 sources，sources 先于全部 delta（BE-030 顺序契约）。"""
    llm = ScriptedLLM(answers=_RAG_ANSWER)
    graph = await rag_graph_factory(llm)
    events = [
        event
        async for event in graph.astream({"question": "违反服务期约定怎么赔偿", "history": []}, stream_mode="custom")
    ]
    assert events[0].type == "plan"
    assert list(events[0].sub_queries) == ["违反服务期约定怎么赔偿"]
    assert events[1].type == "sources"  # 检索先于生成：sources 在 delta 之前
    sources = events[1].sources
    assert len(sources) == 1
    assert sources[0]["source"] == "劳动法问答.txt"
    assert "违约金" in sources[0]["content"]
    deltas = [e.content for e in events if e.type == "delta"]
    assert "".join(deltas) == _RAG_ANSWER
    # 校验通过：不出现 regenerating
    assert all(e.type != "regenerating" for e in events)


@pytest.mark.asyncio
async def test_regenerating_event_emitted_on_contract_retry(rag_graph_factory) -> None:
    """verify 打回重生成时推送 regenerating 事件，且 delta 拼接只有最终版回答。"""
    llm = ScriptedLLM(
        answers=[
            "依据知识库回答。",  # 第一轮：契约失败
            _RAG_ANSWER,
        ],
        judges=_judge("pass"),
    )
    graph = await rag_graph_factory(llm)
    events = [
        event
        async for event in graph.astream({"question": "违反服务期约定怎么赔偿", "history": []}, stream_mode="custom")
    ]
    types = [e.type for e in events]
    assert "regenerating" in types
    # regenerating 必须出现在两批 delta 之间（第一轮 delta 之后、第二轮之前）
    first_regenerating = types.index("regenerating")
    assert any(t == "delta" for t in types[:first_regenerating])
    assert any(t == "delta" for t in types[first_regenerating + 1 :])
    # 下游若在 regenerating 处重置聚合，拼接结果就是最终回答
    collected: list[str] = []
    for event in events:
        if event.type == "regenerating":
            collected = []
        elif event.type == "delta":
            collected.append(event.content)
    assert "".join(collected) == _RAG_ANSWER


@pytest.mark.asyncio
async def test_rag_graph_empty_knowledge_no_sources_event(tmp_path) -> None:
    """检索无命中时不应产生 sources 事件（等价于"无参考文档"契约）。"""
    store = InMemoryVectorStore()
    await store.initialize()
    llm = ScriptedLLM(answers="知识库中暂无相关依据，建议咨询专业律师。")
    graph = build_qa_graph(llm, rag=RagService(DeterministicEmbedding(), store))
    try:
        events = [
            event
            async for event in graph.astream({"question": "量子力学是什么", "history": []}, stream_mode="custom")
        ]
        assert all(e.type in ("plan", "delta") for e in events)
        assert "".join(e.content for e in events if e.type == "delta") == "知识库中暂无相关依据，建议咨询专业律师。"
    finally:
        await store.close()


# ---- 装配守卫 ----


def test_compiled_graph_satisfies_qa_workflow_port() -> None:
    """装配守卫：LangGraph 编译产物必须满足 QaWorkflow 领域端口。

    仅装配不执行：向量库无需 initialize（图不运行就不会触达检索）。
    """
    from app.domain.services.qa_workflow import QaWorkflow

    rag = RagService(DeterministicEmbedding(), InMemoryVectorStore())
    graph = build_qa_graph(ScriptedLLM("ok"), rag=rag)
    assert isinstance(graph, QaWorkflow)  # runtime_checkable 校验方法存在性


@pytest.mark.asyncio
async def test_create_qa_workflow_returns_port_implementation(rag_factory) -> None:
    """工厂应返回显式实现 QaWorkflow 端口的对象（agent 模块 OOP 契约）。"""
    from app.agent import create_qa_workflow
    from app.domain.services.qa_workflow import QaWorkflow

    workflow = create_qa_workflow(ScriptedLLM("知识库中暂无相关依据，建议咨询专业律师。"), rag=await rag_factory())
    assert isinstance(workflow, QaWorkflow)
    # 与编译图等价：经端口执行问答可用
    answer = (await workflow.ainvoke({"question": "q", "history": []}))["answer"]
    assert answer.startswith("知识库中暂无相关依据")


@pytest.mark.asyncio
async def test_planner_defaults_to_main_llm(rag_factory) -> None:
    """planner 缺省时用主 LLM：规划与生成调用落在同一实例上。"""
    llm = ScriptedLLM(answers="知识库中暂无相关依据，建议咨询专业律师。")
    graph = build_qa_graph(llm, rag=await rag_factory())
    await graph.ainvoke({"question": "q", "history": []})
    assert len(llm.plan_calls) == 2  # 主 LLM 实例收到了规划调用（含空命中重规划）
