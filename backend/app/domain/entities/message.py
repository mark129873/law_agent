"""Message 领域实体。

DDD 说明：消息是会话聚合内的一次交互记录，属于典型的实体（有唯一 id、
有生命周期）；role 用枚举而非自由字符串，保证"用户/助手/系统"三种
角色是领域规则的一部分，非法角色在构造前即被拒绝。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.domain.entities.conversation import utc_now


class MessageRole(str, Enum):
    """消息角色。

    为什么用枚举：角色取值固定且会被前端渲染逻辑区分，
    枚举可以防止拼写错误值入库——这是"用类型表达领域约束"的思想：
    让非法状态无法表示，而不是在写入时靠人工校验拦截。
    """

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    """对话中的一条消息（用户问题或模型回答）。"""

    conversation_id: str
    role: MessageRole
    content: str
    id: str = ""
    created_at: datetime = field(default_factory=utc_now)
