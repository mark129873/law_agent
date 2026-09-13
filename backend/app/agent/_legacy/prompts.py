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

# 规划器系统 Prompt（BE-030）：把用户问题拆解为知识库检索用的子查询。
# 为什么要求 JSON 数组：规划结果要被程序消费（逐条检索），结构化输出
# 是节点与模型之间的契约；解析失败时节点侧有回退路径（透传原问题）。
PLANNER_SYSTEM_PROMPT = (
    "你是法律问答系统的检索规划器。你的唯一任务是把用户问题改写为"
    "1~3 个用于知识库检索的子查询，并以 JSON 数组格式输出，"
    "例如：[\"劳动合同到期不续签的经济补偿标准\"]。\n"
    "规则：\n"
    "1. 问题单一明确时，只输出一个子查询，尽量保留用户原问法；\n"
    "2. 问题涉及多个法律主题时（如同时问补偿金和年假），按主题拆成多个子查询；\n"
    "3. 子查询必须是完整的检索短语，不要输出解释、编号或 JSON 以外的任何内容；\n"
    "4. 如果收到上一轮的修正建议，请针对建议补充或改写子查询。"
)

# verify 判分系统 Prompt（BE-030）：对回答做 groundedness 校验。
# 为什么输出三态 verdict：区分"依据不足"（打回规划补检索）与
# "表达契约失败"（打回生成重写），两类缺口的修复路径不同。
VERIFY_JUDGE_SYSTEM_PROMPT = (
    "你是法律问答系统的回答校验器。给定【参考依据】和【回答】，"
    "判断回答是否严格以参考依据为支撑，只输出一个 JSON 对象：\n"
    "{\"verdict\": \"pass|grounding|contract\", \"feedback\": \"...\", "
    "\"unsupported\": [\"无依据的结论\"]}\n"
    "判定规则：\n"
    "1. pass：回答的每个结论都能在参考依据中找到出处（参考依据为空时，"
    "回答明确声明了知识库中暂无相关依据也算 pass）；\n"
    "2. grounding：回答包含参考依据中找不到出处的具体结论"
    "（虚构法条、编造数字等），把无依据的结论逐条列入 unsupported，"
    "并在 feedback 中说明需要补充检索哪些主题；\n"
    "3. contract：回答有依据可用但违反了表达契约（有参考依据却未注明来源，"
    "或参考依据为空却未声明信息不足），在 feedback 中说明违反了什么；\n"
    "4. 只输出 JSON，不要输出任何其他内容。"
)


def build_messages(question: str, context: str, history: list[ChatMessage] | None = None,
                   feedback: str = "") -> list[ChatMessage]:
    """组装发送给模型的完整消息列表。

    为什么把上下文拼进 user 消息而不是独立消息：多数模型对
    "指令+依据+问题"在同一消息内的遵循度更高，也便于模型把
    来源标注与问题对应起来。
    feedback 非空时（verify 打回重生成），附加修正指令让模型
    针对具体问题重写，而不是重新随机生成一版。
    """
    messages: list[ChatMessage] = [ChatMessage(role=MessageRole.SYSTEM, content=LEGAL_SYSTEM_PROMPT)]
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


def build_plan_messages(question: str, feedback: str = "") -> list[ChatMessage]:
    """组装规划器的消息列表（BE-030）。

    规划是独立任务，不携带对话历史：拆解只取决于当前问题本身，
    带历史反而可能让子查询偏向上一轮话题。
    """
    user_content = f"【用户问题】\n{question}"
    if feedback:
        user_content += f"\n\n【修正建议】\n{feedback}"
    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content=PLANNER_SYSTEM_PROMPT),
        ChatMessage(role=MessageRole.USER, content=user_content),
    ]
    return messages


def build_verify_messages(question: str, context: str, answer: str) -> list[ChatMessage]:
    """组装判分器的消息列表（BE-030）。

    判分只需要"问题+依据+回答"三要素，不带历史：校验的对象是
    本次回答与本次检索依据的一致性，历史上下文会引入噪音。
    """
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=VERIFY_JUDGE_SYSTEM_PROMPT),
        ChatMessage(
            role=MessageRole.USER,
            content=(
                f"【用户问题】\n{question}\n\n【参考依据】\n{context or '（空，知识库无命中）'}\n\n"
                f"【回答】\n{answer}"
            ),
        ),
    ]
