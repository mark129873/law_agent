"""子查询生成 Prompt（BE-034，设计 §24）：把复杂问题拆分为独立子查询。"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

SUBQUERY_GENERATOR_SYSTEM_PROMPT = (
    "你是法律知识库的子查询生成器。把复杂问题拆分为多个独立可检索的子查询，"
    "只输出一个 JSON 对象，格式：\n"
    '{"queries": ["子查询一", "子查询二", "子查询三"]}\n'
    "规则：\n"
    "1. 最多 5 条子查询；\n"
    "2. 每条子查询必须：独立、可直接检索、尽量不重叠、共同服务于原始问题；\n"
    "3. 按回答原始问题所需的证据维度拆分（法律依据、计算规则、适用条件、例外情形等）；\n"
    "4. 示例：违法解除劳动合同，工作7年，月薪3万，能赔多少？→ "
    "['违法解除劳动合同的法律依据', '违法解除赔偿金计算规则', '工作年限对应赔偿月数', '高工资的赔偿上限规则']；\n"
    "5. 只输出 JSON，不要输出任何其他内容。"
)


def build_subquery_messages(original_query: str, normalized_query: str) -> list[ChatMessage]:
    """组装子查询生成器的消息列表。"""
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=SUBQUERY_GENERATOR_SYSTEM_PROMPT),
        ChatMessage(role=MessageRole.USER, content=f"【用户问题】\n{normalized_query or original_query}"),
    ]
