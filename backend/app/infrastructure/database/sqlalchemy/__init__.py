"""app/infrastructure/database/sqlalchemy 模块包。

为什么这么做：把「SQLAlchemy 数据库实现」收敛到单一包内，
domain/application 层只看到 Database 与三个 Repository 端口，
数据库技术细节（引擎、方言、类型装饰器）全部封在 infrastructure。
"""

from app.infrastructure.database.sqlalchemy.database import SQLAlchemyDatabase, sqlite_url

__all__ = ["SQLAlchemyDatabase", "sqlite_url"]
