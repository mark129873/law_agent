"""数据库表结构定义（SQLAlchemy Core Table 元数据）。

为什么要单独一个文件：表结构是"存储契约"，集中定义后
建表（create_all）、DML 表达式（insert/select）都引用同一份元数据，
不会出现"SQL 里写的列名和建表语句不一致"这类漂移。

方言无关设计（为 MySQL 8.0 接入铺路）：
- 主键/外键列使用定长 String（VARCHAR）而不是 TEXT——MySQL 的 TEXT
  列不能直接做主键或外键，这是纯 SQLite 写法最容易踩的坑；
- 外键使用**表级** ForeignKey 约束并在其上声明 ON DELETE CASCADE：
  列内联 REFERENCES 在 MySQL 中会被解析后忽略，级联删除会静默失效；
- 时间列统一用 IsoDateTime（见 types.py），保证回读保留时区。
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Index, Integer, MetaData, String, Table, Text

from app.infrastructure.database.sqlalchemy.types import IsoDateTime

# 全部表共享的元数据对象：create_all / DML 表达式都从这里取表
metadata = MetaData()

# 主键为 uuid4().hex（32 个十六进制字符），定长 VARCHAR 在 SQLite/MySQL 上语义一致
_ID_LENGTH = 32

conversations = Table(
    "conversations",
    metadata,
    Column("id", String(_ID_LENGTH), primary_key=True),
    Column("title", Text, nullable=False),
    Column("created_at", IsoDateTime, nullable=False),
)

messages = Table(
    "messages",
    metadata,
    Column("id", String(_ID_LENGTH), primary_key=True),
    # 表级外键 + 级联删除：删除会话时消息由数据库保证一并清理，不留孤儿数据
    Column(
        "conversation_id",
        String(_ID_LENGTH),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("role", String(16), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", IsoDateTime, nullable=False),
    # 参考来源（仅助手消息可能携带）：JSON 数组文本，中文原样存储（ensure_ascii=False）
    Column("sources", Text, nullable=True),
)

# 会话维度的消息查询是最热路径，索引与旧实现保持同名同列
Index("idx_messages_conversation", messages.c.conversation_id)

documents = Table(
    "documents",
    metadata,
    Column("id", String(_ID_LENGTH), primary_key=True),
    Column("filename", Text, nullable=False),
    Column("file_size", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("created_at", IsoDateTime, nullable=False),
)
