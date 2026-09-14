"""思考内容工具（BE-042，决策 D9）：think 事件的文本规整与统一发射。

为什么截断在后端做：text ≤120 字是 SSE 契约的一部分，契约由生产端
统一保证而不是每个消费端各自实现——前端零截断逻辑，后端只此一处
（单一事实源）。为什么提供 emit_think 统一入口：label 复用
NODE_LABELS 中文映射、text 统一截断，各节点只提供节点名与原始内容，
不重复拼接契约细节（DRY）；无消费者时 emit_event 安全丢弃，
图外直调（单元测试）不受影响（与 status/plan 事件同一机制）。
"""

from __future__ import annotations

from app.agent.constants import node_label
from app.agent.events import emit_event
from app.domain.services.qa_workflow import QaStreamEvent

# 思考内容单条上限（决策 D9）：超长尾部以省略号截断——
# 展示性截断，完整理由仍在节点 trace 与结构化日志里可追溯
THINK_MAX_CHARS = 120


def truncate_text(text: str, max_chars: int = THINK_MAX_CHARS) -> str:
    """规整并截断一条思考内容：去首尾空白、折叠换行为空格、超长省略号结尾。

    为什么折叠换行：思考块是行式列表，一条内容占一行；LLM 输出与
    校验理由中可能携带多行文本，不折叠会破坏前端行结构。
    """
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip() + "…"


def emit_think(node: str, text: str) -> None:
    """发射一条 think 事件（节点过程内容行，前端聚合进「思考」块）。

    与 status 事件的分工：status 由包装器统一推节点起止，
    think 由节点自己推"内容"（只有节点知道自己的业务内容）——
    包装器保持不越权（与 trace 同一职责边界）。
    """
    emit_event(
        QaStreamEvent(
            type="think",
            node=node,
            label=node_label(node),
            text=truncate_text(text),
        )
    )
