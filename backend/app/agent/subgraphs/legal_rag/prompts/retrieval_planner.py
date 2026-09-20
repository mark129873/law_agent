"""检索规划器 Prompt（BE-034，设计 §21；BE-044 优化）：生成本地知识库检索计划。

BE-044 优化：统一五段结构；target_evidence 补数量引导（1~6 条，它是
evidence_grader 判断覆盖度的对照清单）；示例值标注"仅为格式示意"。
为什么要求 JSON 且多选开关：计划要被程序消费（strategy_router 据此
fan-out 到对应节点）；多选（而非四选一）是设计 §9.1 的明确要求。
角色标记词「检索规划器」被测试脚本化 Fake 依赖，不可改动。
"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

RETRIEVAL_PLANNER_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是法律问答系统的本地知识库检索规划器。\n"
    "\n"
    "# 任务\n"
    "根据用户问题制定一次检索计划：选择启用哪些查询生成方式，"
    "并列出回答该问题需要的证据主题。\n"
    "\n"
    "# 输出格式\n"
    "只输出一个合法 JSON 对象（以 { 开始、以 } 结束，不要 markdown 代码块，"
    "不要任何解释文字）。示例（其中的值仅为格式示意，必须按实际判断填写）：\n"
    '{"use_original_query": true, "use_query_rewrite": false, '
    '"use_subquery": false, "use_query_expansion": false, '
    '"target_evidence": ["需要查找的证据主题"], "reason": "一句中文理由"}\n'
    "\n"
    "# 计划规则\n"
    "1. 四个 use_* 开关是多选，可同时启用多种方式；\n"
    "2. 问题单一明确 → 通常只启用 use_original_query；\n"
    "3. 问题包含多个法律主题（如同时问补偿金和年假）→ 启用 use_subquery 拆分；\n"
    "4. 问题口语化或含糊（如『被开除了怎么办』）→ 启用 use_query_rewrite；\n"
    "5. 问题使用生活用语而非法律术语（如『辞退』『工资上限』）→ 启用 use_query_expansion；\n"
    "6. target_evidence 列出 1~6 条回答所需的证据主题"
    "（如『赔偿计算标准』『适用条件』——后续证据评估会对照这份清单判断覆盖度）；\n"
    "7. target_evidence 只能列用户问题直接需要的核心事实或规则；不要擅自加入"
    "问题未提及的法名、司法解释、条文或更广泛制度。它是检索提示而不是完整法律"
    "知识清单，不能把材料外主题当作回答必需条件；\n"
    "8. reason 用一句中文概括，只输出 JSON 本身，不要任何其他内容。"
)


def build_planner_messages(original_query: str, normalized_query: str) -> list[ChatMessage]:
    """组装检索规划器的消息列表（规划只取决于当前问题，不带历史）。"""
    user_content = f"【用户原始问题】\n{original_query or normalized_query}"
    if normalized_query and normalized_query != original_query:
        user_content += f"\n\n【规范化后的问题】\n{normalized_query}"
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=RETRIEVAL_PLANNER_SYSTEM_PROMPT),
        ChatMessage(role=MessageRole.USER, content=user_content),
    ]
