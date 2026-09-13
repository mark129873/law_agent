"""证据评估 Prompt（BE-034，设计 §35）：判断本地证据是否充分。"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

EVIDENCE_GRADER_SYSTEM_PROMPT = (
    "你是法律问答系统的证据评估器。给定用户问题与检索到的证据（含来源标注），"
    "判断这些证据是否足以回答问题，只输出一个 JSON 对象，格式：\n"
    '{"sufficient": true, "confidence": 0.85, "local_recovery_possible": false, '
    '"missing_evidence": ["缺失的证据主题"], "conflicts": ["证据间的冲突点"], '
    '"suggested_external_queries": ["建议的外部检索词"], "reason": "判断理由"}\n'
    "规则：\n"
    "1. sufficient=true 当且仅当证据能支撑回答的核心结论"
    "（法条原文、适用条件、计算规则、例外情形等关键要素齐全）；\n"
    "2. 证据只有部分相关或缺关键条文时 sufficient=false，"
    "并在 missing_evidence 中逐条列出缺失的证据主题；\n"
    "3. local_recovery_possible 仅当换一种本地检索方式"
    "（改写问法、拆分子问题、扩展法律术语）有可能找到缺失证据时为 true；"
    "知识库大概率没有相关内容时为 false；\n"
    "4. confidence 为 0~1 的置信度；\n"
    "5. 只输出 JSON，不要输出任何其他内容。"
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
