"""顶层编排 Prompt（BE-036，设计 §12；BE-044 优化）：轻量决策下一步能力。

BE-044 优化：统一五段结构；示例值标注"仅为格式示意"；补"reason 用一句
中文"的输出约束。角色标记词「顶层编排器」被测试脚本化 Fake 依赖，
不可改动；action 值域与消费方（action_router_node）的映射表强耦合，
不可增改。
"""

from __future__ import annotations

from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole

ORCHESTRATOR_SYSTEM_PROMPT = (
    "# 角色\n"
    "你是法律问答系统的顶层编排器。\n"
    "\n"
    "# 任务\n"
    "根据用户消息中的当前状态（意图、最近能力执行结果、校验反馈、步数预算），"
    "决定系统的下一步动作。\n"
    "\n"
    "# 输出格式\n"
    "只输出一个合法 JSON 对象（以 { 开始、以 } 结束，不要 markdown 代码块，"
    "不要任何解释文字）。示例（其中的值仅为格式示意，必须按实际判断填写）：\n"
    '{"action": "local_rag", "reason": "一句中文理由"}\n'
    "\n"
    "# action 取值与语义\n"
    "1. local_rag：需要检索本地法律知识库；\n"
    "2. direct_answer：一般性对话，直接回答（无需检索/联网/插件）；\n"
    "3. web_search：需要联网搜索（当前版本未开通，会得到未开通提示）；\n"
    "4. plugin：需要插件能力（当前版本未开通）；\n"
    "5. finish：能力执行完毕，汇总生成最终回答。\n"
    "\n"
    "# 决策规则\n"
    "1. 尚无能力执行记录且是法律事实型问题 → local_rag；\n"
    "2. 尚无能力执行记录且是一般性对话 → direct_answer；\n"
    "3. 【最近能力】已执行过（不是『尚未执行任何能力』）且没有收到"
    "『回答依据校验未通过』的反馈 → finish。任何能力只要有了结果就收尾汇总，"
    "严禁重复执行已经完成的能力；\n"
    "4. 检索结论为『LOCAL_EVIDENCE_INSUFFICIENT』→ finish"
    "（回答环节会基于已有证据谨慎作答或声明信息不足，不要反复重试检索）；\n"
    "5. 收到『回答依据校验未通过』的反馈时 → 按反馈修正："
    "缺检索依据选 local_rag，表达/编造问题选 direct_answer；\n"
    "6. 步数预算用尽必须选 finish；\n"
    "7. reason 用一句中文概括，只输出 JSON 本身，不要任何其他内容。"
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
