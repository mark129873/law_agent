"""直接回答 Prompt（BE-036，设计 §17；BE-044 优化）：一般性对话不经检索直接回答。

BE-044 优化：补"避免输出法条编号与精确法律数据"的避雷约束——
grounding GENERAL 档会按此校验，此前模型常在闲聊回答里带出法条编号
导致被连续打回（Session 033 实测一次闲聊被打回 3 次）。

为什么不沿用法律检索策略 Prompt（BE-017）：直接回答路径没有知识库
依据可引用，若沿用会让模型输出"知识库中暂无相关依据"这类检索语境
的声明——对问候/概念解释类问题答非所问（D2 决策，PRODUCT.md §3）。
"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

DIRECT_ANSWER_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是法律知识库助手的对话窗口。当前用户输入是一般性对话（问候、感谢、"
    "概念解释、系统功能说明或常识闲聊），不涉及需要检索法律知识库的具体事实问题。\n"
    "\n"
    "# 回答规则\n"
    "1. 自然、简洁地回答，使用简体中文；\n"
    "2. 不要提及知识库、检索或参考依据——本次回答不基于检索；\n"
    "3. 如果用户的问题实际需要法律依据才能准确回答，建议用户提出具体的"
    "法律问题，以便系统查询知识库后给出有据回答。\n"
    "\n"
    "# 禁止事项\n"
    "1. 不要编造或引用具体法条编号（如『第X条』）、案例编号或精确法律数据"
    "（期限、比例、金额等）——这类内容会触发回答校验打回；"
    "用一般性表述代替（如『法律通常规定了明确的期限』）；\n"
    "2. 不要为了显得专业而堆砌虚构的权威来源。"
)


def build_direct_messages(
    question: str, history: list[ChatMessage] | None = None, feedback: str = ""
) -> list[ChatMessage]:
    """组装直接回答的消息列表（带会话历史，保持对话连贯）。

    feedback 非空时（grounding 校验打回重答），附加修正指令。
    """
    messages: list[ChatMessage] = [
        ChatMessage(role=MessageRole.SYSTEM, content=DIRECT_ANSWER_SYSTEM_PROMPT)
    ]
    if history:
        messages.extend(history)
    user_content = question
    if feedback:
        user_content += f"\n\n【修正要求】\n上一版回答存在以下问题，请修正：{feedback}"
    messages.append(ChatMessage(role=MessageRole.USER, content=user_content))
    return messages
