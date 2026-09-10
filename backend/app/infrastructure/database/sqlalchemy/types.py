"""SQLAlchemy 自定义列类型（方言适配点）。

为什么需要这层：领域实体里的时间是**带时区的 datetime**
（`utc_now()` 返回 `datetime.now(timezone.utc)`），并且有测试断言
"读回后 tzinfo 必须存在"。而 MySQL 的 DATETIME 本身没有时区概念，
SQLAlchemy 默认的 DateTime 在 SQLite 方言下也只存不带偏移的字符串，
两者都会在回读时丢掉 tzinfo，让"时间"这一领域语义被存储层改变。

解决方式：自定义 TypeDecorator，把带时区的 datetime 以 ISO-8601
字符串（含 +00:00 偏移）原样存取——TEXT（SQLite）/ VARCHAR(32)（MySQL）
都能承载，回读用 `datetime.fromisoformat` 精确还原。
这是本实现里**唯一**的方言适配点，其余 DDL/DML 全部由 SQLAlchemy
Core 生成，与具体数据库无关（策略模式：把"时间怎么落库"这一可变
细节抽成可替换的策略）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class IsoDateTime(TypeDecorator):
    """时区无损的 datetime 列类型。

    存储格式为 ISO-8601 字符串（例：`2026-09-06T12:00:00.123456+00:00`），
    与迁移前手写 SQL 实现的存储格式完全一致：既保证既有数据库文件
    可直接读取（零数据迁移），也保证中文环境下的可读性与排序语义。
    """

    # 底层类型长度足够容纳 32 字符的 ISO 字符串（含微秒与 +00:00 偏移）
    impl = String(32)
    # cache_ok 告诉 SQLAlchemy 本类型可以安全参与语句编译缓存
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        """写入数据库前：datetime -> ISO 字符串。"""
        if value is None:
            return None
        if not isinstance(value, datetime):
            # 尽早失败：把错误类型挡在存储层之外，而不是写入奇怪的值
            raise TypeError(f"IsoDateTime 只接受 datetime，收到 {type(value)!r}")
        return value.isoformat()

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        """从数据库读出后：ISO 字符串 -> 带时区的 datetime。"""
        if value is None:
            return None
        return datetime.fromisoformat(value)
