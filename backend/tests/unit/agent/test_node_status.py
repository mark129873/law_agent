"""节点状态包装器单元测试（BE-041）。"""

import asyncio

from app.agent.node_status import with_node_status
from app.agent.events import event_emitter_var
from app.domain.services.qa_workflow import QaStreamEvent


def _run_with_capture(node_fn, state):
    """在事件捕获上下文中执行包装节点。"""
    async def _run():
        captured: list[QaStreamEvent] = []
        token = event_emitter_var.set(captured.append)
        try:
            result = await node_fn(state)
        finally:
            event_emitter_var.reset(token)
        return result, captured

    return asyncio.run(_run())


def test_wrapper_emits_start_and_end_with_label_and_duration():
    async def node(state):
        return {"answer": "ok"}

    wrapped = with_node_status("hybrid_retriever_node", node)
    result, events = _run_with_capture(wrapped, {})
    assert result == {"answer": "ok"}
    assert [e.phase for e in events] == ["start", "end"]
    assert all(e.type == "status" for e in events)
    assert events[0].label == "混合检索知识库"  # 中文标签映射
    assert events[0].node == "hybrid_retriever_node"
    assert events[1].duration_ms is not None and events[1].duration_ms >= 0


def test_wrapper_falls_back_to_node_name_for_unknown_label():
    async def node(state):
        return {}

    wrapped = with_node_status("unknown_node_xyz", node)
    _, events = _run_with_capture(wrapped, {})
    assert events[0].label == "unknown_node_xyz"  # 未登记节点回退为节点名


def test_wrapper_emits_end_on_exception_and_reraises():
    async def node(state):
        raise RuntimeError("boom")

    wrapped = with_node_status("evidence_ranking_node", node)

    async def _capture():
        captured: list[QaStreamEvent] = []
        token = event_emitter_var.set(captured.append)
        try:
            await wrapped({})
        except RuntimeError as error:
            assert str(error) == "boom"  # 异常必须原样抛出
        finally:
            event_emitter_var.reset(token)
        return captured

    events = asyncio.run(_capture())
    assert [e.phase for e in events] == ["start", "end"]  # 异常路径也推 end（前端不悬挂）


def test_wrapper_without_consumer_drops_events_silently():
    async def node(state):
        return {}

    wrapped = with_node_status("observation_node", node)
    # 无事件接收器（图外直调）——不抛错
    result = asyncio.run(wrapped({}))
    assert result == {}


# ---- BE-043：Langfuse span 压栈/弹栈（包装器统一采集） ----
class RecordingSink:
    """假 trace 汇：记录 start_span/end 调用。"""

    def __init__(self) -> None:
        self.span_calls: list = []

    def start_trace(self, **kw):
        pass

    def start_span(self, *, node: str, parent=None):
        self.span_calls.append(("start_span", node))
        return RecordingSpan(self.span_calls, node)

    def record_event(self, **kw):
        pass

    def end_trace(self, **kw):
        pass


class RecordingSpan:
    def __init__(self, calls: list, node: str) -> None:
        self._calls = calls
        self._node = node
        self.ended: list = []

    def record_generation(self, **kw):
        pass

    def end(self, *, duration_ms=None, error=None):
        self._calls.append(("end_span", self._node, duration_ms, error))


def test_wrapper_pushes_and_ends_span_when_sink_present():
    """有 sink：start_span(node, parent=外层) → end_span(耗时)。"""
    from app.agent.trace_context import trace_span_var
    from app.domain.services.trace_sink import trace_sink_var as sink_var

    async def node(state):
        return {"ok": True}

    sink = RecordingSink()
    async def _run():
        sink_token = sink_var.set(sink)
        try:
            wrapped = with_node_status("query_router_agent", node)
            result = await wrapped({})
            return result, trace_span_var.get()
        finally:
            sink_var.reset(sink_token)

    result, span_after = asyncio.run(_run())
    assert result == {"ok": True}
    assert sink.span_calls[0] == ("start_span", "query_router_agent")
    end_call = sink.span_calls[1]
    assert end_call[0] == "end_span" and end_call[1] == "query_router_agent"
    assert end_call[3] is None  # 成功路径无 error
    assert span_after is None  # 弹栈后上下文恢复


def test_wrapper_ends_span_with_error_on_exception():
    """异常路径：span.end(error=...) 后异常原样抛出。"""
    from app.domain.services.trace_sink import trace_sink_var as sink_var

    async def node(state):
        raise RuntimeError("节点故障")

    sink = RecordingSink()

    async def _run():
        sink_token = sink_var.set(sink)
        try:
            wrapped = with_node_status("answer_generator_agent", node)
            await wrapped({})
        except RuntimeError:
            pass
        finally:
            sink_var.reset(sink_token)

    asyncio.run(_run())
    end_call = sink.span_calls[1]
    assert end_call[0] == "end_span" and end_call[3] == "节点故障"


def test_wrapper_skips_span_without_sink():
    """无 sink（未启用）：零调用、零干扰。"""
    async def node(state):
        return {}

    wrapped = with_node_status("observation_node", node)
    result, _ = _run_with_capture(wrapped, {})
    assert result == {}
