"""顶层编排 Prompt（BE-036，设计 §12）：轻量决策下一步能力。"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

ORCHESTRATOR_SYSTEM_PROMPT = (
    "你是法律问答系统的顶层编排器。根据当前状态决定下一步动作，"
    "只输出一个 JSON 对象，格式：\n"
    '{"action": "local_rag", "reason": "简要理由"}\n'
    "action 取值与语义：\n"
    "- local_rag：需要检索本地法律知识库；\n"
    "- direct_answer：一般性对话，直接回答（无需检索/联网/插件）；\n"
    "- web_search：需要联网搜索（当前版本未开通，会得到未开通提示）；\n"
    "- plugin：需要插件能力（当前版本未开通）；\n"
    "- finish：能力执行完毕，汇总生成最终回答。\n"
    "决策规则：\n"
    "1. 尚无能力执行记录且问题是法律事实型 → local_rag；\n"
    "2. 尚无能力执行记录且是一般性对话 → direct_answer；\n"
    "3. 知识库检索已有结果（无论充分与否）→ finish（汇总生成回答）；\n"
    "4. 直接回答已生成 → finish；\n"
    "5. 检索结论为『LOCAL_EVIDENCE_INSUFFICIENT』→ finish"
    "（回答环节会基于已有证据谨慎作答或声明信息不足，不要反复重试检索）；\n"
    "6. 收到『回答依据校验未通过』的反馈时 → direct_answer"
    "（带着反馈修正回答），除非反馈显示缺的是检索依据；\n"
    "7. 步数预算用尽必须选 finish；\n"
    "8. 只输出 JSON，不要输出任何其他内容。"
)


def build_orchestrator_messages(
    question: str,
    intent: str,
    request_type: str,
    last_capability: str,
    capability_status: str,
    global_step_count: int,
    max_global_steps: int,
    grounding_issues: list[str] | None = None,
) -> list[ChatMessage]:
    """组装编排器的消息列表：问题 + 意图 + 最近能力结果 + 预算余量。"""
    user_content = (
        f"【用户问题】\n{question}\n"
        f"【意图】\n{intent or '未知'}（请求类型：{request_type or '未知'}）\n"
        f"【最近能力】\n{last_capability or '（尚未执行任何能力）'}"
        f" 状态：{capability_status or '无'}\n"
        f"【步数预算】\n已用 {global_step_count}/{max_global_steps}"
    )
    if grounding_issues:
        user_content += "\n【回答依据校验未通过的反馈】\n" + "；".join(grounding_issues)
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=ORCHESTRATOR_SYSTEM_PROMPT),
        ChatMessage(role=MessageRole.USER, content=user_content),
    ]
