"""证据评估 Prompt（BE-034，设计 §35；BE-044 优化）：判断本地证据是否充分。

BE-044 优化：统一五段结构；消除示例 sufficient:true 的锚定偏差
（示例值写死 true 会诱导模型倾向判充分，而本节点代码安全默认是
"不充分"——宁可多检索不可误判充分，两者必须同向）；补 missing_evidence
的下游用途说明（它是恢复规划的输入）。角色标记词「证据评估器」被测试
脚本化 Fake 依赖，不可改动。
"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

EVIDENCE_GRADER_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是法律问答系统的证据评估器。\n"
    "\n"
    "# 任务\n"
    "给定用户问题（及当初计划的证据主题清单）与检索到的证据（含来源标注），"
    "判断这些证据是否足以回答问题。\n"
    "\n"
    "# 输出格式\n"
    "只输出一个合法 JSON 对象（以 { 开始、以 } 结束，不要 markdown 代码块，"
    "不要任何解释文字）。示例（其中的值仅为格式示意，必须按证据实际判断填写）：\n"
    '{"sufficient": true, "confidence": 0.85, "local_recovery_possible": false, '
    '"missing_evidence": ["缺失的证据主题"], "conflicts": ["证据间的冲突点"], '
    '"suggested_external_queries": ["建议的外部检索词"], "reason": "一句中文判断理由"}\n'
    "\n"
    "# 判定规则\n"
    "1. sufficient=true 当且仅当证据能支撑回答的核心结论"
    "（法条原文、适用条件、计算规则、例外情形等关键要素齐全）；\n"
    "2. 宁可判不充分，不可误判充分：证据只有部分相关或缺关键条文时"
    "sufficient=false，并在 missing_evidence 中逐条列出缺失的证据主题"
    "（该清单是下一轮检索恢复计划的直接输入）；\n"
    "3. local_recovery_possible 仅当换一种本地检索方式"
    "（改写问法、拆分子问题、扩展法律术语）有可能找到缺失证据时为 true；"
    "知识库大概率没有相关内容时为 false；\n"
    "4. confidence 为 0~1 的置信度，与判定保持一致；\n"
    "5. 只输出 JSON 本身，不要任何其他内容。"
)


def build_grader_messages(
    original_query: str,
    evidence_context: str,
    target_evidence: list[str] | None = None,
) -> list[ChatMessage]:
    """组装证据评估器的消息列表。

    target_evidence 来自检索计划（retrieval_planner 产出），
    让评估者对照"当初想找什么"判断覆盖度，而不是只看字面相似。
    """
    user_content = f"【用户问题】\n{original_query}"
    if target_evidence:
        user_content += "\n\n【需要的证据主题】\n" + "；".join(target_evidence)
    user_content += f"\n\n【检索到的证据】\n{evidence_context or '（空，知识库无命中）'}"
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=EVIDENCE_GRADER_SYSTEM_PROMPT),
        ChatMessage(role=MessageRole.USER, content=user_content),
    ]
