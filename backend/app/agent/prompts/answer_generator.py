"""回答生成 Prompt（BE-036，设计 §18；BE-044 优化）：能力结果 → 最终回答草稿。

回答策略沿用 BE-017（法律问答系统 Prompt）：优先依据知识库上下文
回答并注明来源文件；依据为空或不足时明确告知"知识库中暂无相关依据，
建议咨询专业律师"；严禁虚构法律条文、案例编号或结论，先给结论再给依据。

BE-044 优化：明确【来源：文件名】的标注格式与示例——grounding 规则档
按该字面检查（缺标注会被打回重生成），此前措辞只说"注明来源文件"，
GLM 偶发漏写导致多一轮重生成；补"简洁不重复、不堆砌无关条文"约束
（真实 E2E 曾出现结论句重复）。字面锚点「优先依据」「知识库中暂无
相关依据」「禁止」「严禁虚构」被 test_answer_strategy 断言，不可改动。
"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

ANSWER_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是一名专业的中国法律咨询助手。请严格遵守以下回答策略。\n"
    "\n"
    "# 回答规则\n"
    "1. 优先依据【参考依据】中提供的知识库内容回答用户问题；\n"
    "2. 回答中凡引用了知识库依据的地方，必须在句末以【来源：文件名】格式标注"
    "（例如：……自申请日起计算。【来源：中华人民共和国专利法.txt】），"
    "文件名必须与依据中给出的完全一致；\n"
    "3. 如果参考依据为空，或不足以回答问题，必须明确告知用户"
    "\"知识库中暂无相关依据，建议咨询专业律师\"，禁止编造答案；\n"
    "4. 严禁虚构法律条文、案例编号或结论；引用条文时保持原文准确；\n"
    "5. 回答使用简体中文，结构清晰：先给结论，再给依据，最后列来源；\n"
    "6. 简洁不重复：同一结论只说一次，不堆砌与问题无关的条文，"
    "不逐字复述大段依据原文。\n"
    "\n"
    "# 禁止事项\n"
    "禁止编造知识库中不存在的法条、案例或数字；禁止遗漏来源标注；"
    "禁止输出与本次回答无关的内容。"
)

WEB_ANSWER_RULES = (
    "\n\n# 联网搜索补充规则\n"
    "本次【参考依据】来自 Tavily 联网搜索，不是本地知识库；只能依据给出的网页标题、地址和正文回答。"
    "回答涉及网页事实时，使用【来源：网页标题】标注，标题必须与依据中的标题一致；"
    "不得补写依据中没有的事实，不得把搜索结果当作法律意见。"
)


def build_answer_messages(
    question: str,
    context: str,
    history: list[ChatMessage] | None = None,
    feedback: str = "",
    web_search: bool = False,
) -> list[ChatMessage]:
    """组装回答生成的消息列表。

    为什么把上下文拼进 user 消息而不是独立消息：模型对
    "指令+依据+问题"在同一消息内的遵循度更高（BE-017 已验证）。
    feedback 非空时（grounding 打回重答），附加修正指令。
    """
    system_prompt = ANSWER_SYSTEM_PROMPT + (WEB_ANSWER_RULES if web_search else "")
    messages: list[ChatMessage] = [ChatMessage(role=MessageRole.SYSTEM, content=system_prompt)]
    if history:
        messages.extend(history)
    if context:
        user_content = f"【参考依据】\n{context}\n\n【用户问题】\n{question}"
    else:
        user_content = question
    if feedback:
        user_content += f"\n\n【修正要求】\n上一版回答存在以下问题，请在保持格式的前提下修正：{feedback}"
    messages.append(ChatMessage(role=MessageRole.USER, content=user_content))
    return messages
