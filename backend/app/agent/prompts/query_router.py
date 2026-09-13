"""意图路由 Prompt（BE-036，设计 §11.1）：规范化问题 + 识别意图 + 判断请求类型。"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

QUERY_ROUTER_SYSTEM_PROMPT = (
    "你是法律问答系统的意图路由器。对用户输入做三件事：规范化问题、识别意图、"
    "判断应该由哪种能力处理，只输出一个 JSON 对象，格式：\n"
    '{"normalized_query": "规范化后的问题", "intent": "legal_question", '
    '"request_type": "local_rag", "extracted_conditions": {"金额": "3万"}}\n'
    "intent 取值：\n"
    "- legal_question：法律事实型问题（法条、赔偿、程序、权利义务等）→ request_type=local_rag；\n"
    "- general_question：一般性对话（问候、感谢、概念解释、系统功能说明、常识闲聊）"
    "→ request_type=direct；\n"
    "- web_request：明确要求联网/搜索最新网络信息 → request_type=web；\n"
    "- plugin_request：要求使用插件/工具能力（如日历、计算器插件）→ request_type=plugin；\n"
    "- other：无法归类 → request_type=direct。\n"
    "规则：\n"
    "1. 拿不准是否需要法律依据时，倾向 legal_question（宁可多检索不可漏依据）；\n"
    "2. 提到具体法律条文、案例、赔偿计算、诉讼程序的一律算 legal_question；\n"
    "3. normalized_query 保留原意，补全省略的主语与法律要素，去掉口语冗余；\n"
    "4. extracted_conditions 提取基础条件（金额/年限/城市/行为等），没有就留空对象；\n"
    "5. 只输出 JSON，不要输出任何其他内容。"
)


def build_router_messages(question: str) -> list[ChatMessage]:
    """组装意图路由器的消息列表（路由只取决于当前输入，不带历史）。"""
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=QUERY_ROUTER_SYSTEM_PROMPT),
        ChatMessage(role=MessageRole.USER, content=f"【用户输入】\n{question}"),
    ]
