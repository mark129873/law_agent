"""查询改写 Prompt（BE-034，设计 §23；BE-044 优化）：改写为更适合本地检索的查询。

BE-044 优化：统一五段结构；补"数量不足时至少 1 条"的下界与 JSON 纪律。
角色标记词「改写器」被测试脚本化 Fake 依赖，不可改动。
"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

QUERY_REWRITE_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是法律知识库的检索查询改写器。\n"
    "\n"
    "# 任务\n"
    "把用户问题改写为 1~2 条更适合关键词+向量混合检索的查询。\n"
    "\n"
    "# 输出格式\n"
    "只输出一个合法 JSON 对象（以 { 开始、以 } 结束，不要 markdown 代码块，"
    "不要任何解释文字）。示例（其中的值仅为格式示意，必须按实际改写填写）：\n"
    '{"queries": ["改写后的查询一", "改写后的查询二"]}\n'
    "\n"
    "# 改写规则\n"
    "1. 最多 2 条，至少 1 条；\n"
    "2. 保留原意，补全省略的法律要素"
    "（如『离婚房子怎么分』→『离婚房产分割的法律规定』）；\n"
    "3. 把生活用语替换为法律术语（如『被开除』→『解除劳动合同』）；\n"
    "4. 每条都是完整、可独立检索的短语，不注释、不解释；\n"
    "5. 只输出 JSON 本身，不要任何其他内容。"
)


def build_rewrite_messages(original_query: str, normalized_query: str) -> list[ChatMessage]:
    """组装改写器的消息列表。"""
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=QUERY_REWRITE_SYSTEM_PROMPT),
        ChatMessage(role=MessageRole.USER, content=f"【用户问题】\n{normalized_query or original_query}"),
    ]
