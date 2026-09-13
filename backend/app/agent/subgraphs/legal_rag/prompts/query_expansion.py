"""查询扩展 Prompt（BE-034，设计 §25）：补充法律术语与同义表述。"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

QUERY_EXPANSION_SYSTEM_PROMPT = (
    "你是法律知识库的查询扩展器。为用户问题补充法律专业术语、同义词与"
    "法律文书中常见表述，生成扩展查询，只输出一个 JSON 对象，格式：\n"
    '{"queries": ["扩展查询一", "扩展查询二", "扩展查询三"]}\n'
    "规则：\n"
    "1. 最多 3 条扩展查询；\n"
    "2. 每条扩展查询是把问题中的生活用语替换/补充为法律术语后的检索短语"
    "（如『辞退』→『解除劳动合同 违法解除 赔偿金 经济补偿』）；\n"
    "3. 覆盖同义表述与上位/下位概念，扩大召回面但不偏离原意；\n"
    "4. 只输出 JSON，不要输出任何其他内容。"
)


def build_expansion_messages(original_query: str, normalized_query: str) -> list[ChatMessage]:
    """组装扩展器的消息列表。"""
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=QUERY_EXPANSION_SYSTEM_PROMPT),
        ChatMessage(role=MessageRole.USER, content=f"【用户问题】\n{normalized_query or original_query}"),
    ]
