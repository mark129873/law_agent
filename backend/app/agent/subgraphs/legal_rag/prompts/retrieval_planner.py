"""检索规划器 Prompt（BE-034，设计 §21）：生成本地知识库检索计划。"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

# 为什么要求 JSON 且多选开关：计划要被程序消费（strategy_router 据此
# fan-out 到对应节点）；多选（而非四选一）是设计 §9.1 的明确要求。
RETRIEVAL_PLANNER_SYSTEM_PROMPT = (
    "你是法律问答系统的本地知识库检索规划器。根据用户问题制定检索计划，"
    "只输出一个 JSON 对象，格式：\n"
    '{"use_original_query": true, "use_query_rewrite": false, '
    '"use_subquery": false, "use_query_expansion": false, '
    '"target_evidence": ["需要查找的证据主题"], "reason": "简要理由"}\n'
    "规则：\n"
    "1. 四个 use_* 开关是多选，可以同时启用多种方式；\n"
    "2. 问题单一明确 → 通常只用原始问题（use_original_query）；\n"
    "3. 问题包含多个法律主题（如同时问补偿金和年假）→ 启用 use_subquery 拆分；\n"
    "4. 问题口语化或含糊（如『被开除了怎么办』）→ 启用 use_query_rewrite；\n"
    "5. 问题使用生活用语而非法律术语（如『辞退』『工资上限』）→ 启用 use_query_expansion；\n"
    "6. target_evidence 列出回答该问题需要的证据主题（用于后续评估证据覆盖度）；\n"
    "7. 只输出 JSON，不要输出任何其他内容。"
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
