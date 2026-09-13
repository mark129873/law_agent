"""回答生成 Prompt（BE-036，设计 §18）：能力结果 → 最终回答草稿。

回答策略沿用 BE-017（法律问答系统 Prompt）：优先依据知识库上下文
回答并注明来源文件；依据为空或不足时明确告知"知识库中暂无相关依据，
建议咨询专业律师"；严禁虚构法律条文、案例编号或结论，先给结论再给依据。
"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

ANSWER_SYSTEM_PROMPT = (
    "你是一名专业的中国法律咨询助手。请严格遵守以下回答策略：\n"
    "1. 优先依据【参考依据】中提供的知识库内容回答用户问题，并注明引用的来源文件；\n"
    "2. 如果参考依据为空，或不足以回答问题，必须明确告知用户"
    "\"知识库中暂无相关依据，建议咨询专业律师\"，禁止编造答案；\n"
    "3. 严禁虚构法律条文、案例编号或结论；引用条文时保持原文准确；\n"
    "4. 回答使用简体中文，结构清晰，先给结论再给依据。"
)


def build_answer_messages(
    question: str,
    context: str,
    history: list[ChatMessage] | None = None,
    feedback: str = "",
) -> list[ChatMessage]:
    """组装回答生成的消息列表。

    为什么把上下文拼进 user 消息而不是独立消息：模型对
    "指令+依据+问题"在同一消息内的遵循度更高（BE-017 已验证）。
    feedback 非空时（grounding 打回重答），附加修正指令。
    """
    messages: list[ChatMessage] = [
        ChatMessage(role=MessageRole.SYSTEM, content=ANSWER_SYSTEM_PROMPT)
    ]
    if history:
        messages.extend(history)
    if context:
        user_content = f"【参考依据】\n{context}\n\n【用户问题】\n{question}"
    else:
        user_content = question
    if feedback:
        user_content += f"\n\n【修正要求】\n上一版回答存在以下问题，请在保持格式的前提下修正：{feedback}"
    messages.append(ChatMessage(role=MessageRole.USER, content=user_content))
    return messages
