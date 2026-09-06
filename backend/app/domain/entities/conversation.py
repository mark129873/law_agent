"""Conversation 领域实体。

为什么用纯 dataclass：实体是领域层的核心契约，
不依赖 pydantic/ORM/数据库技术，保证领域层可独立测试与演进；
HTTP 层的序列化由 API 层 DTO 负责，与实体解耦。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utc_now() -> datetime:
    """统一的当前时间函数（UTC）。

    为什么统一在这里：各实体时间字段必须使用同一时区与精度，
    否则排序与展示会出现不一致。
    """
    return datetime.now(timezone.utc)


@dataclass
class Conversation:
    """一次对话会话，包含若干条 Message。"""

    title: str
    id: str = ""
    created_at: datetime = field(default_factory=utc_now)
