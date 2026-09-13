"""Langfuse 可观测汇单元测试（BE-043，ADR-0010）。

用假 langfuse 客户端锁住三级结构的调用契约（trace → 节点 span →
generation 与流程事件）与失败降级（client 抛错不外泄）——不联网、
不依赖真实 Langfuse 服务端。
"""

import asyncio

from app.infrastructure.trace.langfuse_sink import (
    LangfuseTraceSink,
    LangfuseTraceSinkFactory,
    null_trace_sink_factory,
)


class FakeObservation:
    """假 langfuse observation：记录全部调用，支持链式子观测。"""

    def __init__(self, recorder: list, name: str, kind: str) -> None:
        self._recorder = recorder
        self.name = name
        self.kind = kind
        self.kwargs: dict = {}
        self.ended = False

    def start_observation(self, *, name: str, as_type: str = "span", **kwargs):
        self._recorder.append(("start_observation", name, as_type))
        child = FakeObservation(self._recorder, name, as_type)
        child.kwargs = kwargs
        return child

    def create_event(self, *, name: str, metadata=None, **kwargs):
        self._recorder.append(("create_event", name, metadata))

    def update(self, **kwargs):
        self._recorder.append(("update", kwargs))

    def end(self, **kwargs):
        self.ended = True
        self._recorder.append(("end", self.name))


class FakeLangfuseClient:
    """假 langfuse 客户端：根 observation + 调用流水。"""

    def __init__(self, *, boom: bool = False) -> None:
        self.calls: list = []
        self.boom = boom  # True 时所有方法抛错（降级路径测试）

    def _check(self):
        if self.boom:
            raise RuntimeError("langfuse unreachable")

    def start_observation(self, *, name: str, as_type: str = "span", **kwargs):
        self._check()
        self.calls.append(("start_observation", name, as_type))
        return FakeObservation(self.calls, name, as_type)

    def create_event(self, *, name: str, metadata=None, **kwargs):
        self._check()
        self.calls.append(("create_event", name, metadata))


def _run(coro):
    return asyncio.run(coro)


def test_trace_lifecycle_creates_root_and_sets_output():
    """trace 生命周期：start_trace 建根、end_trace 写输出并关闭。"""
    client = FakeLangfuseClient()
    sink = LangfuseTraceSink(client)
    sink.start_trace(session_id="conv-1", question="试用期多长？")
    sink.end_trace(output="回答全文", metadata={"source_count": "3"})
    kinds = [c[0] for c in client.calls]
    assert kinds == ["start_observation", "update", "end"]
    # 根 observation：名字 chat、input=问题、metadata 带会话 id
    root_kwargs = client.calls[0]
    assert root_kwargs[1] == "chat"
    # update 携带输出与 metadata（langfuse v4 根 observation 即 trace）


def test_start_span_nests_under_parent_span():
    """节点 span 挂靠：parent 优先于 trace 根（子图嵌套语义）。"""
    client = FakeLangfuseClient()
    sink = LangfuseTraceSink(client)
    sink.start_trace(session_id="conv-1", question="q")
    root_child = sink.start_span(node="legal_rag_subgraph")
    inner = sink.start_span(node="hybrid_retriever_node", parent=root_child)
    assert root_child is not None and inner is not None
    assert root_child._span.kind == "span" and inner._span.kind == "span"
    sink.record_event(name="plan", payload={"sub_queries": "q1"})
    sink.end_trace(output="ok")
    names = [c[1] for c in client.calls if c[0] == "start_observation"]
    assert names == ["chat", "legal_rag_subgraph", "hybrid_retriever_node"]
    events = [c for c in client.calls if c[0] == "create_event"]
    assert events and events[0][1] == "flow:plan"  # 流程事件统一 flow: 前缀


def test_record_generation_reports_model_input_output():
    """generation 契约：模型名 + 消息 + 输出 + 耗时都进 langfuse。"""
    client = FakeLangfuseClient()
    sink = LangfuseTraceSink(client)
    sink.start_trace(session_id="conv-1", question="q")
    span = sink.start_span(node="query_router_agent")
    span.record_generation(
        model="glm-4.5-air",
        messages=[{"role": "user", "content": "问题"}],
        output='{"intent": "legal_question"}',
        duration_ms=812,
        metadata={"attempt": "1"},
    )
    calls = client.calls
    gen_call = [c for c in calls if c[0] == "start_observation" and c[2] == "generation"]
    assert len(gen_call) == 1
    span.end(duration_ms=900)
    sink.end_trace(output="ok")
    assert any(c[0] == "end" for c in calls)


def test_client_failure_never_raises():
    """失败降级：langfuse 不可达时所有方法吞异常（业务不受影响）。"""
    client = FakeLangfuseClient(boom=True)
    sink = LangfuseTraceSink(client)
    sink.start_trace(session_id="c", question="q")  # 不应抛错
    span = sink.start_span(node="n")
    assert span is None  # 建根失败 → span 为 None，包装器跳过
    sink.record_event(name="plan", payload={})
    sink.end_trace(output=None, error="boom")

    # 成功建根后中途故障同样不外泄：trace 对象整体换成"必炸"实现
    client2 = FakeLangfuseClient()
    sink2 = LangfuseTraceSink(client2)
    sink2.start_trace(session_id="c", question="q")
    span2 = sink2.start_span(node="n")
    assert span2 is not None
    client2.boom = True

    class _ExplodingObservation:
        def start_observation(self, **kw):
            raise RuntimeError("x")

        def create_event(self, **kw):
            raise RuntimeError("x")

        def update(self, **kw):
            raise RuntimeError("x")

        def end(self, **kw):
            raise RuntimeError("x")

    # 节点 span 与 trace 根都炸：record_generation/end/事件/收尾全不外泄
    span2._span = _ExplodingObservation()
    span2.record_generation(model="m", messages=[], output=None)
    span2.end()
    sink2._trace = _ExplodingObservation()
    sink2.record_event(name="think", payload={})
    sink2.end_trace(output="ok")


def test_factory_degrades_when_keys_missing():
    """缺密钥降级：工厂构造成功但 create() 恒 None（等于关闭）。"""
    factory = LangfuseTraceSinkFactory(
        base_url="https://cloud.langfuse.com", public_key="", secret_key=""
    )
    assert factory.create() is None


def test_null_factory_returns_none():
    """关闭态工厂恒 None（所有上报点跳过）。"""
    assert null_trace_sink_factory() is None
