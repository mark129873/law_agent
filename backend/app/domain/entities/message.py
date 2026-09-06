"""Message 领域实体。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.domain.entities.conversation import utc_now


class MessageRole(str, Enum):
    """消息角色。

    为什么用枚举：角色取值固定且会被前端渲染逻辑区分，
    枚举可以防止拼写错误值入库。
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
