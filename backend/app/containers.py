"""应用级依赖装配点。

为什么全应用只有一个装配点：所有"抽象接口 -> 具体实现"的映射
集中在此处，切换 Provider 时只改配置与这里的工厂注册，
业务代码与分层结构完全不动，依赖关系一目了然。
"""

from __future__ import annotations

from app.common.di import DIContainer
from app.config.settings import Settings, get_settings
from app.infrastructure.database.base import Database
from app.infrastructure.database.sqlite.database import SQLiteDatabase


def _build_database(settings: Settings) -> Database:
    """按配置构造数据库实现（工厂函数）。

    为什么在工厂里分支：新增 MySQL 支持时只需在此增加分支并引入实现类，
    业务层与装配结构完全不动。
    """
    if settings.db_provider.value == "sqlite":
        return SQLiteDatabase(settings.sqlite_db_path)
    # MySQL 实现将在后续版本提供（见 feature_list 架构预留）
    raise NotImplementedError(
        f"数据库 Provider '{settings.db_provider.value}' 尚未实现；"
        f"当前可用：sqlite"
    )


def create_container(settings: Settings | None = None) -> DIContainer:
    """创建并装配应用容器。

    为什么允许传入 settings：测试可以注入自定义配置构造容器，
    生产路径则默认读取 get_settings() 单例。
    """
    settings = settings or get_settings()
    container = DIContainer()
    # 配置本身作为单例注册，后续工厂通过容器解析配置来决定实现
    container.register(Settings, lambda c: settings, singleton=True)
    # 数据库：按 DB_PROVIDER 配置注册对应实现（BE-005）
    container.register(Database, lambda c: _build_database(settings), singleton=True)

    # BE-006/BE-009 落地后，向量库、LLM Provider 的具体工厂将在此处注册。
    return container
