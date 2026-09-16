"""回答依据校验 Prompt（BE-036，设计 §19；BE-044 优化）：grounding 与引用一致性检查。

BE-044 优化（降误判是重点——judge 误判会触发整轮重生成）：
RAG 档补"实质一致即可，不要求逐字匹配"与"声明信息不足的合法回答
判通过"；GENERAL 档补"与法律权威无关的数字（序号、日常数字）不算
法律数据"——针对 Session 033 记录的闲聊被连续打回 3 次。
为什么区分两条路径的判定标准：检索路径的证据是"回答的
唯一合法事实来源"，标准是严格 groundedness；直接回答路径没有检索
依据，标准只是"不编造权威引用"——用同一把尺子会把正常闲聊判死。
角色标记词「回答校验器」被测试脚本化 Fake 依赖，不可改动。
"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

GROUNDING_RAG_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是法律问答系统的回答校验器。\n"
    "\n"
    "# 任务\n"
    "给定【参考依据】和【回答】（回答基于知识库检索生成），"
    "判断回答是否严格以参考依据为支撑。\n"
    "\n"
    "# 输出格式\n"
    "只输出一个合法 JSON 对象（以 { 开始、以 } 结束，不要 markdown 代码块，"
    "不要任何解释文字）。示例（其中的值仅为格式示意，必须按实际判断填写）：\n"
    '{"passed": true, "unsupported_claims": ["无依据的结论"], '
    '"citation_issues": ["引用与来源不一致的问题"], "reason": "一句中文判定理由"}\n'
    "\n"
    "# 判定规则\n"
    "1. passed=true：回答的每个结论都能在参考依据中找到实质出处，"
    "且引用的来源文件名与依据一致；\n"
    "2. 实质一致即可：条文用自己的话转述、与来源措辞不同但含义相符，"
    "不算不一致——不要求逐字匹配；\n"
    "3. 回答包含参考依据中找不到出处的具体结论（虚构法条、编造数字等）"
    "→ passed=false，把无依据的结论逐条列入 unsupported_claims；\n"
    "4. 回答引用的来源文件名在参考依据中不存在，或所引内容与该来源"
    "实质相悖 → passed=false，列入 citation_issues；\n"
    "5. 回答为『知识库中暂无相关依据』类的信息不足声明（依据确实不足时）"
    "属于合法回答，判 passed=true；\n"
    "6. 只输出 JSON 本身，不要任何其他内容。"
)

GROUNDING_GENERAL_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是法律问答系统的回答校验器。\n"
    "\n"
    "# 任务\n"
    "本次回答来自一般性对话（未经知识库检索，无参考依据），"
    "只需检查回答是否编造了权威引用。\n"
    "\n"
    "# 输出格式\n"
    "只输出一个合法 JSON 对象（以 { 开始、以 } 结束，不要 markdown 代码块，"
    "不要任何解释文字）。示例（其中的值仅为格式示意，必须按实际判断填写）：\n"
    '{"passed": true, "unsupported_claims": [], "citation_issues": [], "reason": "一句中文判定理由"}\n'
    "\n"
    "# 判定规则\n"
    "1. passed=true：回答没有编造具体法条编号（如『第X条』）、案例编号、"
    "精确法律数据（期限、比例、金额等）或虚构权威来源；\n"
    "2. 回答出现上述编造的权威引用 → passed=false，列入 citation_issues；\n"
    "3. 以下情况不算编造，必须判 passed=true：一般性观点、常识、建议；"
    "与法律权威无关的数字（列表序号、功能数量、日常数量等）；"
    "不含具体编号与精确数值的一般性法律常识表述；\n"
    "4. 宁可放行不可误杀：拿不准时判 passed=true（校验是增强不是闸门）；\n"
    "5. 只输出 JSON 本身，不要任何其他内容。"
)

GROUNDING_WEB_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是法律问答系统的回答校验器。\n"
    "\n"
    "# 任务\n"
    "给定来自联网搜索的网页依据和回答，判断回答是否严格由网页内容支撑。\n"
    "\n"
    "# 输出格式\n"
    "只输出一个合法 JSON 对象（以 { 开始、以 } 结束，不要 markdown 代码块，不要任何解释文字）。\n"
    '{"passed": true, "unsupported_claims": [], "citation_issues": [], "reason": "一句中文判定理由"}\n'
    "\n"
    "# 判定规则\n"
    "1. 每个具体结论都必须能在网页依据中找到实质出处；\n"
    "2. 回答引用来源时，标题必须与网页依据标题一致，并使用【来源：网页标题】；\n"
    "3. 依据中没有的事实、数字或结论必须判 passed=false；\n"
    "4. 只输出 JSON 本身，不要任何其他内容。"
)


def build_grounding_messages(
    question: str,
    context: str,
    answer: str,
    web_search: bool = False,
) -> list[ChatMessage]:
    """组装校验器的消息列表；context 为空时自动切换为一般对话校验标准。"""
    if web_search:
        system = GROUNDING_WEB_SYSTEM_PROMPT
    else:
        system = GROUNDING_RAG_SYSTEM_PROMPT if context else GROUNDING_GENERAL_SYSTEM_PROMPT
    context_block = context if context else "（空——本次回答未经知识库检索）"
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=system),
        ChatMessage(
            role=MessageRole.USER,
            content=f"【用户问题】\n{question}\n\n【参考依据】\n{context_block}\n\n【回答】\n{answer}",
        ),
    ]
