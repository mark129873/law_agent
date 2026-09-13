"""谨慎回答 Prompt（BE-036，设计 §28 对应主图 fallback）：预算耗尽后的兜底回答。"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

FALLBACK_SYSTEM_PROMPT = (
    "你是法律咨询助手。回答生成与依据校验的修正次数已达上限，"
    "需要基于已有的可靠证据给出谨慎、保守的回答。直接输出回答文本"
    "（本节点不使用结构化输出），规则：\n"
    "1. 只陈述有依据支撑的内容，引用来源文件；\n"
    "2. 对无法确认的部分明确说明\"这一点暂无法确认，建议咨询专业律师\"；\n"
    "3. 不新增任何未经依据支撑的结论；\n"
    "4. 回答使用简体中文，简洁清晰。"
)


def build_fallback_messages(
    question: str,
    context: str,
    issues: list[str],
) -> list[ChatMessage]:
    """组装兜底回答的消息列表：问题 + 可靠依据 + 未通过的校验反馈。"""
    user_content = f"【用户问题】\n{question}\n\n【可靠依据】\n{context or '（空）'}"
    if issues:
        user_content += "\n\n【未通过的校验反馈】\n" + "；".join(issues)
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=FALLBACK_SYSTEM_PROMPT),
        ChatMessage(role=MessageRole.USER, content=user_content),
    ]
