"""法律问答 Prompt 与回答策略测试（BE-017）。

策略的三条硬规则必须在系统 Prompt 中显式存在：
优先依据知识库、无依据时明确说明、禁止虚构法条。
"""

from app.agent._legacy.prompts import LEGAL_SYSTEM_PROMPT, build_messages
from app.domain.entities.message import MessageRole


def test_system_prompt_contains_core_strategy() -> None:
    """核心策略关键词必须全部出现在系统 Prompt 中。"""
    assert "优先依据" in LEGAL_SYSTEM_PROMPT
    assert "知识库中暂无相关依据" in LEGAL_SYSTEM_PROMPT
    assert "禁止" in LEGAL_SYSTEM_PROMPT
    assert "严禁虚构" in LEGAL_SYSTEM_PROMPT


def test_with_context_marks_reference_section() -> None:
    """有检索依据时，用户消息应包含参考依据段并保留来源标注。"""
    messages = build_messages("试用期多长？", "【来源：劳动法.txt】\n试用期不得超过六个月")
    assert messages[0].role is MessageRole.SYSTEM
    assert messages[-1].role is MessageRole.USER
    assert "【参考依据】" in messages[-1].content
    assert "【来源：劳动法.txt】" in messages[-1].content
    assert "试用期多长？" in messages[-1].content


def test_without_context_question_passes_through() -> None:
    """无依据时用户消息就是原始问题，交由模型按策略声明信息不足。"""
    messages = build_messages("试用期多长？", "")
    assert messages[-1].content == "试用期多长？"
    assert len(messages) == 2  # system + user，无多余内容
