"""思考内容工具单元测试（BE-042，决策 D9）。

覆盖 truncate_text 的规整与截断规则（换行折叠、省略号、上限）、
emit_think 的契约拼装（label 中文映射 + text 截断 + 类型）——
全部纯函数或内存 Fake 发射器，无 IO。
"""

from app.agent.events import event_emitter_var
from app.agent.utils import THINK_MAX_CHARS, emit_think, truncate_text
from app.domain.services.qa_workflow import QaStreamEvent


def test_truncate_text_folds_newlines_and_strips():
    """多行文本折叠为单行（思考块一条内容占一行）。"""
    assert truncate_text("  第一行\n\n第二行  ") == "第一行 第二行"


def test_truncate_text_short_passes_through():
    """不超上限的文本原样保留。"""
    assert truncate_text("证据评估：证据充分") == "证据评估：证据充分"


def test_truncate_text_cuts_long_text_with_ellipsis():
    """超长文本截断到上限并以省略号结尾（契约保证 ≤上限）。"""
    text = "长" * (THINK_MAX_CHARS + 50)
    result = truncate_text(text)
    assert result.startswith("长" * THINK_MAX_CHARS)
    assert result.endswith("…")
    assert len(result) == THINK_MAX_CHARS + 1


def test_truncate_text_handles_empty_and_none_like_input():
    """空输入返回空串（节点可能在异常路径发空内容）。"""
    assert truncate_text("") == ""
    assert truncate_text("   \n  ") == ""


def test_emit_think_builds_contract_fields():
    """emit_think 组装契约：type=node/label（中文映射）/text（已截断）。"""
    received: list[QaStreamEvent] = []
    token = event_emitter_var.set(received.append)
    try:
        emit_think("hybrid_retriever_node", "并发检索 2 条查询，命中 8 条候选")
    finally:
        event_emitter_var.reset(token)
    assert len(received) == 1
    event = received[0]
    assert event.type == "think"
    assert event.node == "hybrid_retriever_node"
    assert event.label == "混合检索知识库"  # NODE_LABELS 中文映射
    assert event.text == "并发检索 2 条查询，命中 8 条候选"


def test_emit_think_truncates_overlong_text():
    """发射前统一截断——生产端保证 SSE 契约 text ≤120 字。"""
    received: list[QaStreamEvent] = []
    token = event_emitter_var.set(received.append)
    try:
        emit_think("grounding_checker_agent", "理" * (THINK_MAX_CHARS + 30))
    finally:
        event_emitter_var.reset(token)
    assert len(received[0].text) == THINK_MAX_CHARS + 1
    assert received[0].text.endswith("…")
