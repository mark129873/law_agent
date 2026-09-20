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
    "1. sufficient=true：检索证据已经足以对用户问题作出安全、直接的回答；"
    "以用户问题为范围，不能把 target_evidence 中超出问题的旁支主题当成必答清单；\n"
    "2. 【知识库边界优先】target_evidence 只是上游计划的参考假设，不是材料外法律"
    "规则的必答清单。若计划擅自写入证据中没有出现、且用户没有明确询问的法名、"
    "司法解释、条文或扩展制度，不得把它们列为 missing_evidence；已有直接法条足以"
    "回答用户核心问题时，不得因缺少更广泛的法律背景而判定不充分；\n"
    "3. 对问题明确提出的多个部分，逐项检查核心结论；缺少其中一个核心部分时"
    "sufficient=false。若已有直接法条或足以支持核心结论的证据，不要因为缺少"
    "相邻制度、诉讼细节或模型自行扩展的主题而判不足；合理释义可以回答，但不得补造事实；\n"
    "4. 【错误前提与范围】用户问题中的错误前提与检索证据发生冲突时，不要把这种冲突"
    "当成证据不足；只要证据直接纠正前提并能回答纠正后的问题，sufficient=true。"
    "‘基本限制’‘主要要求’等问题不要求穷尽所有边缘规定；只要问题明确列出的每个"
    "对象都有直接依据，即可在有边界的范围内判定充分。\n"
    "5. 【全称状态定义】只有‘所有主体’‘所有数据’‘全部情形’‘每一家’‘任何主体’"
    "‘一定构成’‘永久存储’等词确实限定问题范围时，才按全称或绝对表述处理；"
    "‘土地所有权’‘所有权人’中的‘所有’是法律术语，不是全称范围。若问题含多个"
    "真正的全称限定，即使局部证据足以反驳用户前提，也不能返回 sufficient=true；"
    "证据没有覆盖全部主体、数据范围和期限时，应在 missing_evidence/reason 中说明边界。\n"
    "6. 宁可判不充分，不可误判充分：确实缺关键条文时"
    "sufficient=false，并在 missing_evidence 中逐条列出缺失的证据主题"
    "（该清单是下一轮检索恢复计划的直接输入）；\n"
    "7. missing_evidence 要尽量保留可检索锚点：法条号、期限/数字、主体、条件和"
    "法名；不要只写『相关规定』或『更多信息』；\n"
    "8. local_recovery_possible 仅当换一种本地检索方式"
    "（改写问法、拆分子问题、扩展法律术语）有可能找到缺失证据时为 true；"
    "知识库大概率没有相关内容时为 false；\n"
    "9. confidence 为 0~1 的置信度，与判定保持一致；\n"
    "10. 只输出 JSON 本身，不要任何其他内容。"
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
