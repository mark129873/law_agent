"""Agent Prompt 组装。

为什么集中在此处：回答策略（要求依据知识库、信息不足时明说）
是法律问答的核心业务规则，全部收敛到本文件，
后续调优策略不会波及工作流与 Provider 代码。
"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

# 法律问答系统 Prompt（BE-017 策略）：
# 1. 优先依据知识库上下文回答；2. 无依据时明确说明信息不足；3. 禁止虚构法条与案例
LEGAL_SYSTEM_PROMPT = (
    "你是一名专业的中国法律咨询助手。请严格遵守以下回答策略：\n"
    "1. 优先依据【参考依据】中提供的知识库内容回答用户问题，并注明引用的来源文件；\n"
    "2. 如果参考依据为空，或不足以回答问题，必须明确告知用户"
    "\"知识库中暂无相关依据，建议咨询专业律师\"，禁止编造答案；\n"
    "3. 严禁虚构法律条文、案例编号或结论；引用条文时保持原文准确；\n"
    "4. 回答使用简体中文，结构清晰，先给结论再给依据。"
)


def build_messages(question: str, context: str, history: list[ChatMessage] | None = None) -> list[ChatMessage]:
    """组装发送给模型的完整消息列表。

    为什么把上下文拼进 user 消息而不是独立消息：多数模型对
    "指令+依据+问题"在同一消息内的遵循度更高，也便于模型把
    来源标注与问题对应起来。
    """
    messages: list[ChatMessage] = [ChatMessage(role=MessageRole.SYSTEM, content=LEGAL_SYSTEM_PROMPT)]
    if history:
        messages.extend(history)
    if context:
        user_content = f"【参考依据】\n{context}\n\n【用户问题】\n{question}"
    else:
        user_content = question
    messages.append(ChatMessage(role=MessageRole.USER, content=user_content))
    return messages
