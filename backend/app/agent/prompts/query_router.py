"""意图路由 Prompt（BE-036，设计 §11.1；BE-044 优化）：规范化问题 + 识别意图 + 判断请求类型。

BE-044 优化：统一五段结构（角色/任务/格式/字段/规则）；
示例值标注"仅为格式示意"消除锚定偏差；JSON 纪律明确禁 markdown 代码块
（减少 LLMService 容错解析与重试）。角色标记词「意图路由器」被测试
脚本化 Fake 依赖，不可改动。
"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

QUERY_ROUTER_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是法律问答系统的意图路由器。\n"
    "\n"
    "# 任务\n"
    "对用户输入完成三件事：①规范化问题；②识别意图；③判断应由哪种能力处理。\n"
    "\n"
    "# 输出格式\n"
    "只输出一个合法 JSON 对象（以 { 开始、以 } 结束，不要 markdown 代码块，"
    "不要任何解释文字）。示例（其中的值仅为格式示意，必须按实际判断填写）：\n"
    '{"normalized_query": "规范化后的问题", "intent": "legal_question", '
    '"request_type": "local_rag", "extracted_conditions": {}}\n'
    "\n"
    "# 字段取值\n"
    "intent 与 request_type 必须是以下五组对应取值之一：\n"
    "1. legal_question：法律事实型问题（法条、赔偿、程序、权利义务、案例分析）"
    "→ request_type=local_rag；\n"
    "2. general_question：一般性对话（问候、感谢、概念解释、系统功能说明、常识闲聊）"
    "→ request_type=direct；\n"
    "3. web_request：明确要求联网或搜索最新网络信息 → request_type=web；\n"
    "4. plugin_request：要求使用插件/工具能力（如日历、计算器插件）→ request_type=plugin；\n"
    "5. other：无法归类 → request_type=direct。\n"
    "extracted_conditions：提取金额/年限/城市/行为等基础条件，键值用中文，没有则留空对象 {}。\n"
    "\n"
    "# 判定规则\n"
    "1. 拿不准是否需要法律依据时，倾向 legal_question——宁可多检索，不可漏依据；\n"
    "2. 提到具体法律条文、案例、赔偿计算、诉讼程序的，一律判 legal_question；\n"
    "3. normalized_query 保留原意：补全省略的主语与法律要素，去掉口语冗余，"
    "不改变事实内容；\n"
    "4. 只输出 JSON 本身，不要任何其他内容。"
)


def build_router_messages(question: str) -> list[ChatMessage]:
    """组装意图路由器的消息列表（路由只取决于当前输入，不带历史）。"""
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=QUERY_ROUTER_SYSTEM_PROMPT),
        ChatMessage(role=MessageRole.USER, content=f"【用户输入】\n{question}"),
    ]
