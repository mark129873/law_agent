"""ChatService trace 采集单元测试（BE-043，ADR-0010）。

用假会话服务 + 假问答图 + 假 trace 汇锁定应用层接线契约：
start_trace → 流程事件（plan/sources/think/regenerating）→ end_trace
（正常输出/异常路径），以及未启用时零调用。纯内存，无数据库。
"""

import asyncio

from app.application.services.chat_service import ChatService
from app.domain.entities.message import MessageRole
from app.domain.services.qa_workflow import QaStreamEvent
from app.domain.services.trace_sink import trace_sink_var


class FakeConversationService:
    """假会话服务：duck-typing，只提供 ChatService 用到的两个方法。"""

    def __init__(self) -> None:
        self.messages: list = []

    async def get_messages(self, conversation_id: str):
        return []

    async def add_message(self, conversation_id: str, role, content, sources=None):
        self.messages.append((role, content, sources))


class FakeQaWorkflow:
    """假问答工作流：按脚本顺序产出事件；可注入异常模拟图失败。"""

    def __init__(self, events: list, error: Exception | None = None) -> None:
        self._events = events
        self._error = error

    async def astream(self, input: dict, **kwargs):
        for event in self._events:
            yield event
        if self._error is not None:
            raise self._error

    async def ainvoke(self, input: dict, **kwargs):
        return {}


class RecordingSink:
    """假 trace 汇：记录全部调用序。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def start_trace(self, *, session_id: str, question: str) -> None:
        self.calls.append(("start_trace", session_id, question))

    def start_span(self, *, node: str, parent=None):
        self.calls.append(("start_span", node))
        return None

    def record_event(self, *, name: str, payload: dict) -> None:
        self.calls.append(("record_event", name, dict(payload)))

    def end_trace(self, *, output: str | None = None, error: str | None = None, metadata=None) -> None:
        self.calls.append(("end_trace", output, error))


def _run_chat(events, sink_factory, error=None):
    async def _run():
        conversations = FakeConversationService()
        graph = FakeQaWorkflow(events, error=error)
        sink_holder: list = []
        def factory():
            return None  # 占位，真正断言用外挂 sink 记录器
        service = ChatService(
            conversation_service=conversations,
            qa_graph=graph,
            trace_sink_factory=sink_factory,
        )
        collected = []
        async for event in service.stream_answer("conv-1", "试用期多长？"):
            collected.append(event)
        return conversations, collected

    return asyncio.run(_run())


def test_trace_lifecycle_and_flow_events_in_order():
    """正常路径：start_trace → plan/sources/think 事件 → end_trace(output)。"""
    sink = RecordingSink()
    events = [
        QaStreamEvent(type="plan", sub_queries=("试用期多长",)),
        QaStreamEvent(type="sources", sources=({"source": "a.txt", "content": "x"},)),
        QaStreamEvent(type="think", node="query_router_agent", label="理解问题", text="意图判定"),
        QaStreamEvent(type="status", node="answer_generator_agent", label="生成回答", phase="start"),
        QaStreamEvent(type="delta", content="回答"),
        QaStreamEvent(type="delta", content="全文"),
    ]
    conversations, collected = _run_chat(events, lambda: sink)
    # 业务事件全部转发（status/think 不进聚合）
    assert [e.type for e in collected] == ["plan", "sources", "think", "status", "delta", "delta"]
    # trace 调用序：start → flow 事件（status 不记录）→ end（聚合后的完整回答）
    assert sink.calls[0] == ("start_trace", "conv-1", "试用期多长？")
    flow_names = [c[1] for c in sink.calls if c[0] == "record_event"]
    assert flow_names == ["plan", "sources", "think"]
    end_call = sink.calls[-1]
    assert end_call == ("end_trace", "回答全文", None)
    # 会话持久化不受 trace 影响
    assert conversations.messages[0][1] == "试用期多长？"
    assert conversations.messages[1][1] == "回答全文"


def test_trace_error_path_records_error_and_reraises():
    """异常路径：end_trace(error=...) 后异常原样上抛。"""
    sink = RecordingSink()
    events = [QaStreamEvent(type="delta", content="半截")]

    async def _run():
        service = ChatService(
            conversation_service=FakeConversationService(),
            qa_graph=FakeQaWorkflow(events, error=RuntimeError("模型超时")),
            trace_sink_factory=lambda: sink,
        )
        try:
            async for _ in service.stream_answer("conv-1", "q"):
                pass
            raise AssertionError("应当上抛")
        except RuntimeError as error:
            assert str(error) == "模型超时"

    asyncio.run(_run())
    assert sink.calls[0][0] == "start_trace"
    assert sink.calls[-1] == ("end_trace", None, "模型超时")


def test_disabled_factory_means_no_trace_calls():
    """未启用（工厂返回 None）：事件照常转发，无任何 trace 调用。"""
    events = [QaStreamEvent(type="delta", content="回答")]
    conversations, collected = _run_chat(events, lambda: None)
    assert [e.type for e in collected] == ["delta"]
    assert conversations.messages[1][1] == "回答"


def test_contextvar_reset_after_stream():
    """请求结束后上下文清空：后续代码读不到上一请求的 sink。"""
    sink = RecordingSink()
    events = [QaStreamEvent(type="delta", content="x")]

    async def _run():
        service = ChatService(
            conversation_service=FakeConversationService(),
            qa_graph=FakeQaWorkflow(events),
            trace_sink_factory=lambda: sink,
        )
        async for _ in service.stream_answer("conv-1", "q"):
            pass
        return trace_sink_var.get()

    assert asyncio.run(_run()) is None
