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
