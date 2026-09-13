"""恢复规划 Prompt（BE-034，设计 §36）：检索失败后的本地补救计划。"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

RECOVERY_PLANNER_SYSTEM_PROMPT = (
    "你是法律知识库检索的恢复规划器。上一轮知识库检索证据不足，"
    "请选择下一轮要执行的补救动作，只输出一个 JSON 对象，格式：\n"
    '{"actions": ["query_rewrite"], "reason": "补救理由", '
    '"missing_evidence": ["缺失的证据主题"]}\n'
    "规则：\n"
    "1. actions 只能从 query_rewrite（改写问法）、subquery（拆分子问题）、"
    "query_expansion（扩展法律术语）中选择，可以多选；\n"
    "2. 严禁选择联网搜索、插件等本地之外的动作；\n"
    "3. 【已执行策略】中列出的策略若已失败，避免原样重复（可换角度再改写）；\n"
    "4. 针对 missing_evidence 的缺口选择最可能补上缺口的动作；\n"
    "5. 只输出 JSON，不要输出任何其他内容。"
)


def build_recovery_messages(
    original_query: str,
    missing_evidence: list[str],
    executed_strategies: list[str],
    retry_count: int,
) -> list[ChatMessage]:
    """组装恢复规划器的消息列表。

    为什么传入已执行策略与重试计数：设计 §36 要求避免重复执行同样
    失败的策略——上下文里显式列出，比让模型自己猜更可靠。
    """
    user_content = f"【用户原始问题】\n{original_query}\n"
    user_content += f"\n【已执行策略】\n{'、'.join(executed_strategies) or '（无）'}"
    user_content += f"\n【当前重试轮次】\n第 {retry_count} 轮"
    if missing_evidence:
        user_content += "\n【缺失证据】\n" + "；".join(missing_evidence)
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=RECOVERY_PLANNER_SYSTEM_PROMPT),
        ChatMessage(role=MessageRole.USER, content=user_content),
    ]
