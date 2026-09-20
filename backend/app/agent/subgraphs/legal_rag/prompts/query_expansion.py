"""查询扩展 Prompt（BE-034，设计 §25；BE-044 优化）：补充法律术语与同义表述。

BE-044 优化：统一五段结构；补"不偏离原意、不引入新法律主题"的反向
约束（扩展的目的是扩大召回面而非偏题）。角色标记词「扩展器」被测试
脚本化 Fake 依赖，不可改动。
"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

QUERY_EXPANSION_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是法律知识库的查询扩展器。\n"
    "\n"
    "# 任务\n"
    "为用户问题补充法律专业术语、同义词与法律文书中常见表述，"
    "生成最多 3 条扩展查询。\n"
    "\n"
    "# 输出格式\n"
    "只输出一个合法 JSON 对象（以 { 开始、以 } 结束，不要 markdown 代码块，"
    "不要任何解释文字）。示例（其中的值仅为格式示意，必须按实际扩展填写）：\n"
    '{"queries": ["扩展查询一", "扩展查询二", "扩展查询三"]}\n'
    "\n"
    "# 扩展规则\n"
    "1. 每条扩展查询是把问题中的生活用语替换/补充为法律术语后的检索短语"
    "（如『辞退』→『解除劳动合同 违法解除 赔偿金 经济补偿』）；\n"
    "2. 覆盖同义表述与上位/下位概念，扩大召回面；\n"
    "3. 不偏离原意：不引入问题之外的新法律主题，不改变问题的事实前提；\n"
    "4. 如果输入包含【本轮必须补齐的证据缺口】，每条查询必须保留其中的法条号、"
    "期限/数字、主体等精确锚点，并围绕该锚点补充同义法律术语；不得只输出宽泛主题；\n"
    "5. 只输出 JSON 本身，不要任何其他内容。"
)


def build_expansion_messages(
    original_query: str,
    normalized_query: str,
    missing_evidence: list[str] | None = None,
) -> list[ChatMessage]:
    """组装扩展器的消息列表。"""
    user_content = f"【用户问题】\n{normalized_query or original_query}"
    if missing_evidence:
        user_content += "\n\n【本轮必须补齐的证据缺口】\n" + "；".join(missing_evidence)
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=QUERY_EXPANSION_SYSTEM_PROMPT),
        ChatMessage(role=MessageRole.USER, content=user_content),
    ]
