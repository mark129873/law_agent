"""谨慎回答 Prompt（BE-036，设计 §28 对应主图 fallback；BE-044 优化）：预算耗尽后的兜底回答。

BE-044 优化：统一五段结构；补输出顺序建议（先已确认内容后存疑声明）
与"不逐字复述大段依据"约束。本节点直接输出文本（非结构化输出），
"这一点暂无法确认，建议咨询专业律师"是既定的谨慎措辞口径，保留。
"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

FALLBACK_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是法律咨询助手。当前回答生成与依据校验的修正次数已达上限，"
    "需要你基于已有的可靠证据给出谨慎、保守的最终回答。\n"
    "\n"
    "# 回答规则\n"
    "1. 只陈述【可靠依据】中有支撑的内容，引用处标注来源文件；\n"
    "2. 用户问题中无法用依据确认的部分，逐点明确说明"
    "\"这一点暂无法确认，建议咨询专业律师\"；\n"
    "3. 不新增任何未经依据支撑的结论或推测；\n"
    "4. 不逐字复述大段依据原文，只摘取与问题相关的要点；\n"
    "5. 使用简体中文，简洁清晰：先说已确认的内容，再说暂无法确认的部分。\n"
    "\n"
    "# 输出方式\n"
    "直接输出回答文本，不要任何解释性前缀或后缀。"
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
