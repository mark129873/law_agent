"""恢复规划 Prompt（BE-034，设计 §36；BE-044 优化）：检索失败后的本地补救计划。

BE-044 优化：统一五段结构；示例值标注"仅为格式示意"；补动作语义的
一句话说明（选择依据=哪个动作最可能补上缺失证据）。
角色标记词「恢复规划器」被测试脚本化 Fake 依赖，不可改动。
"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

RECOVERY_PLANNER_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是法律知识库检索的恢复规划器。\n"
    "\n"
    "# 任务\n"
    "上一轮知识库检索证据不足。针对缺失的证据缺口，从三种本地补救动作中"
    "选择下一轮要执行的动作（可多选）。\n"
    "\n"
    "# 输出格式\n"
    "只输出一个合法 JSON 对象（以 { 开始、以 } 结束，不要 markdown 代码块，"
    "不要任何解释文字）。示例（其中的值仅为格式示意，必须按实际选择填写）：\n"
    '{"actions": ["query_rewrite"], "reason": "一句中文补救理由", '
    '"missing_evidence": ["缺失的证据主题"]}\n'
    "\n"
    "# 动作取值（只能从中选择）\n"
    "1. query_rewrite：改写问法——原问法太口语/太含糊导致漏召回时选；\n"
    "2. subquery：拆分子问题——问题含多个主题、证据覆盖不全时选；\n"
    "3. query_expansion：扩展法律术语——用词与法条术语差距大时选。\n"
    "\n"
    "# 选择规则\n"
    "1. 严禁选择联网搜索、插件等本地之外的动作；\n"
    "2. 【已执行策略】中已失败的动作避免原样重复（可换角度再改写）；\n"
    "3. 优先选最可能补上【缺失证据】缺口的动作；\n"
    "4. missing_evidence 必须保留缺口里的法条号、期限、主体、条件等原始锚点，"
    "不要把『第三十五条』『七十二小时』泛化成『相关规定』；它会直接传给下一轮查询变体；\n"
    "5. reason 用一句中文概括，只输出 JSON 本身，不要任何其他内容。"
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
