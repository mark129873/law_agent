"""未开通能力说明 Prompt（BE-036）。

这个 Prompt 只负责 Web/Plugin Stub 的能力边界说明，不再与 grounding
预算耗尽的回答收尾共用「兜底」命名。这样可以让能力说明和回答生成职责
保持单一：Stub 负责报告能力状态，回答节点负责把状态转成用户可读文本。
"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole


CAPABILITY_NOTICE_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是法律咨询助手，负责向用户清楚说明当前未开通的外部能力。\n"
    "\n"
    "# 任务与输入说明\n"
    "用户请求需要网络搜索或插件能力，但系统当前只开放本地法律知识库问答。\n"
    "\n"
    "# 输出格式\n"
    "直接输出一段简洁的中文说明性回答。\n"
    "\n"
    "# 判定/执行规则\n"
    "1. 明确说明请求所需的外部能力尚未开通或暂不可用；\n"
    "2. 不编造网络搜索结果、插件结果或外部法规内容；\n"
    "3. 建议用户直接提出法律问题，系统将基于本地法律知识库回答。\n"
    "\n"
    "# 输出纪律\n"
    "不要添加解释性前缀，不要声称已经执行了不可用的外部操作。"
)


def build_capability_notice_messages(
    question: str,
    issues: list[str],
) -> list[ChatMessage]:
    """组装未开通能力说明：保留原问题和状态原因，便于模型准确告知用户。"""
    user_content = f"【用户问题】\n{question}"
    if issues:
        user_content += "\n\n【能力状态】\n" + "；".join(issues)
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=CAPABILITY_NOTICE_SYSTEM_PROMPT),
        ChatMessage(role=MessageRole.USER, content=user_content),
    ]
