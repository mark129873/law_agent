"""回答依据校验 Prompt（BE-036，设计 §19）：grounding 与引用一致性检查。"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

# 为什么区分两条路径的判定标准（ADR-0006）：检索路径的证据是"回答的
# 唯一合法事实来源"，标准是严格 groundedness；直接回答路径没有检索
# 依据，标准只是"不编造权威引用"——用同一把尺子会把正常闲聊判死。
GROUNDING_RAG_SYSTEM_PROMPT = (
    "你是法律问答系统的回答校验器。给定【参考依据】和【回答】"
    "（回答基于知识库检索生成），判断回答是否严格以参考依据为支撑，"
    "只输出一个 JSON 对象，格式：\n"
    '{"passed": true, "unsupported_claims": ["无依据的结论"], '
    '"citation_issues": ["引用与来源不一致的问题"], "reason": "判定理由"}\n'
    "判定规则：\n"
    "1. passed=true：回答的每个结论都能在参考依据中找到出处，"
    "且引用的来源文件名与依据一致；\n"
    "2. 回答包含参考依据中找不到出处的具体结论（虚构法条、编造数字等）"
    "→ passed=false，把无依据的结论逐条列入 unsupported_claims；\n"
    "3. 回答引用的来源文件名在参考依据中不存在，或条文内容与来源不符"
    "→ passed=false，列入 citation_issues；\n"
    "4. 只输出 JSON，不要输出任何其他内容。"
)

GROUNDING_GENERAL_SYSTEM_PROMPT = (
    "你是法律问答系统的回答校验器。本次回答来自一般性对话"
    "（未经知识库检索，无参考依据），只需检查回答是否编造了权威引用，"
    "只输出一个 JSON 对象，格式：\n"
    '{"passed": true, "unsupported_claims": [], "citation_issues": [], "reason": "判定理由"}\n'
    "判定规则：\n"
    "1. passed=true：回答没有编造具体法条编号、案例编号、法律数据"
    "（数字、比例、期限等）或虚构权威来源；\n"
    "2. 回答出现了具体法条/案例编号或精确法律数据（在没有依据的情况下）"
    "→ passed=false，列入 citation_issues；\n"
    "3. 一般性观点、常识、建议不算编造；\n"
    "4. 只输出 JSON，不要输出任何其他内容。"
)


def build_grounding_messages(
    question: str,
    context: str,
    answer: str,
) -> list[ChatMessage]:
    """组装校验器的消息列表；context 为空时自动切换为一般对话校验标准。"""
    system = GROUNDING_RAG_SYSTEM_PROMPT if context else GROUNDING_GENERAL_SYSTEM_PROMPT
    context_block = context if context else "（空——本次回答未经知识库检索）"
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=system),
        ChatMessage(
            role=MessageRole.USER,
            content=f"【用户问题】\n{question}\n\n【参考依据】\n{context_block}\n\n【回答】\n{answer}",
        ),
    ]
