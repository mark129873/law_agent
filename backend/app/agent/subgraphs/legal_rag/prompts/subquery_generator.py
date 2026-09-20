"""子查询生成 Prompt（BE-034，设计 §24；BE-044 优化）：把复杂问题拆分为独立子查询。

BE-044 优化：统一五段结构；示例保留（已是该组 Prompt 中唯一带完整
few-shot 示例的，实测有效）。角色标记词「子查询生成器」被测试脚本化
Fake 依赖，不可改动。
"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

SUBQUERY_GENERATOR_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是法律知识库的子查询生成器。\n"
    "\n"
    "# 任务\n"
    "把复杂问题拆分为多个独立可检索的子查询（最多 5 条）。\n"
    "\n"
    "# 输出格式\n"
    "只输出一个合法 JSON 对象（以 { 开始、以 } 结束，不要 markdown 代码块，"
    "不要任何解释文字）。示例（其中的值仅为格式示意，必须按实际拆分填写）：\n"
    '{"queries": ["子查询一", "子查询二", "子查询三"]}\n'
    "\n"
    "# 拆分规则\n"
    "1. 每条子查询必须：独立、可直接检索、尽量不重叠、共同服务于原始问题；\n"
    "2. 按回答原始问题所需的证据维度拆分（法律依据、计算规则、适用条件、例外情形等）；\n"
    "3. few-shot 示例：违法解除劳动合同，工作7年，月薪3万，能赔多少？→\n"
    "   queries=[\"违法解除劳动合同的法律依据\", \"违法解除赔偿金计算规则\", "
    "\"工作年限对应赔偿月数\", \"高工资的赔偿上限规则\"]；\n"
    "4. 恢复检索时若给出证据缺口，应优先把每个缺口拆成独立查询，"
    "保留其中的法条号、期限/数字、主体等精确锚点，不得改成泛化主题；\n"
    "5. 只输出 JSON 本身，不要任何其他内容。"
)


def build_subquery_messages(
    original_query: str,
    normalized_query: str,
    missing_evidence: list[str] | None = None,
) -> list[ChatMessage]:
    """组装子查询生成器的消息列表。"""
    user_content = f"【用户问题】\n{normalized_query or original_query}"
    if missing_evidence:
        user_content += "\n\n【本轮必须补齐的证据缺口】\n" + "；".join(missing_evidence)
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=SUBQUERY_GENERATOR_SYSTEM_PROMPT),
        ChatMessage(role=MessageRole.USER, content=user_content),
    ]
