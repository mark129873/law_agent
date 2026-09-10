"""数据库表结构：SQLAlchemy 2.0 声明式 ORM 模型（BE-025）。

为什么单独一个文件：表结构是"存储契约"，声明式模型是它的唯一真相来源
（`Base.metadata` 同时供 create_all 与将来的 Alembic autogenerate 使用），
不会再出现"建表语句与读写代码不一致"的漂移。

与领域层的关系（DDD 边界，重要）：
- 这些模型**只属于 infrastructure**。领域层是纯 dataclass 实体，
  由 AST 守护测试禁止导入 sqlalchemy，所以 ORM 模型不可能充当领域实体；
- 两个模型体系之间的转换集中在 mappers.py（Data Mapper 模式），
  仓储出口只返回领域实体，ORM 模型不越过 infrastructure 边界。

方言无关设计（为 MySQL 8.0 接入铺路）：
- 主键/外键列使用定长 String（VARCHAR）而不是 TEXT——MySQL 的 TEXT 列
  不能直接做主键或外键，这是纯 SQLite 写法最容易踩的坑；
- 外键使用**表级** ForeignKey 约束并声明 ON DELETE CASCADE：
  列内联 REFERENCES 在 MySQL 中会被解析后忽略，级联删除会静默失效；
- 时间列统一用 IsoDateTime（见 types.py），保证回读保留时区。

刻意不定义 relationship：本项目没有聚合内导航需求（消息永远按
conversation_id 显式查询），不定义关系就没有异步懒加载（MissingGreenlet）
这一整类风险；级联删除由数据库外键保证，不依赖 ORM 的 cascade。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.infrastructure.database.sqlalchemy.types import IsoDateTime

# 主键为 uuid4().hex（32 个十六进制字符），定长 VARCHAR 在 SQLite/MySQL 上语义一致
_ID_LENGTH = 32


class Base(DeclarativeBase):
    """全部 ORM 模型的公共基类；`Base.metadata` 即建表/Alembic 的元数据入口。"""


class ConversationModel(Base):
    """conversations 表：一次对话会话。"""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(_ID_LENGTH), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(IsoDateTime, nullable=False)


class MessageModel(Base):
    """messages 表：会话内的一条消息（用户提问或模型回答）。"""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(_ID_LENGTH), primary_key=True)
    # 表级外键 + 级联删除：删除会话时消息由数据库保证一并清理，不留孤儿数据
    conversation_id: Mapped[str] = mapped_column(
        String(_ID_LENGTH),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(IsoDateTime, nullable=False)
    # 参考来源（仅助手消息可能携带）：JSON 数组文本，中文原样存储（ensure_ascii=False）。
    # 为什么不用 SQLAlchemy 的 JSON 类型：沿用既有数据库文件的存储格式（逐字节一致、
    # 中文可读），避免默认 json.dumps 把中文转成 \uXXXX 转义。
    sources: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 会话维度的消息查询是最热路径，索引与既有数据库保持同名同列
    __table_args__ = (Index("idx_messages_conversation", "conversation_id"),)


class DocumentModel(Base):
    """documents 表：知识库文档元数据（文本内容存放在向量数据库）。"""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(_ID_LENGTH), primary_key=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(IsoDateTime, nullable=False)
