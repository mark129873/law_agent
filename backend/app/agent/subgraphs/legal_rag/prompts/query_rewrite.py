"""查询改写 Prompt（BE-034，设计 §23）：改写为更适合本地检索的查询。"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

QUERY_REWRITE_SYSTEM_PROMPT = (
    "你是法律知识库的检索查询改写器。把用户问题改写为更适合检索的查询，"
    "只输出一个 JSON 对象，格式：\n"
    '{"queries": ["改写后的查询一", "改写后的查询二"]}\n'
    "规则：\n"
    "1. 最多 2 条改写查询；\n"
    "2. 保留原意，补全省略的法律要素（如『离婚房子怎么分』→『离婚房产分割的法律规定』）；\n"
    "3. 把生活用语替换为法律术语（如『被开除』→『解除劳动合同』）；\n"
    "4. 每条都是完整、可独立检索的短语，不要解释；\n"
    "5. 只输出 JSON，不要输出任何其他内容。"
)


def build_rewrite_messages(original_query: str, normalized_query: str) -> list[ChatMessage]:
    """组装改写器的消息列表。"""
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=QUERY_REWRITE_SYSTEM_PROMPT),
        ChatMessage(role=MessageRole.USER, content=f"【用户问题】\n{normalized_query or original_query}"),
    ]
