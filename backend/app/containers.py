"""应用级依赖装配点。

为什么全应用只有一个装配点：所有"抽象接口 -> 具体实现"的映射
集中在此处，切换 Provider 时只改配置与这里的工厂注册，
业务代码与分层结构完全不动，依赖关系一目了然。
"""

from __future__ import annotations

from app.common.di import DIContainer
from app.config.settings import Settings, get_settings


def create_container(settings: Settings | None = None) -> DIContainer:
    """创建并装配应用容器。

    为什么允许传入 settings：测试可以注入自定义配置构造容器，
    生产路径则默认读取 get_settings() 单例。
    """
    settings = settings or get_settings()
    container = DIContainer()
    # 配置本身作为单例注册，后续工厂通过容器解析配置来决定实现
    container.register(Settings, lambda c: settings, singleton=True)

    # BE-004/BE-006/BE-009 落地后，数据库、向量库、LLM Provider
    # 的具体工厂将在此处按 settings.db_provider 等配置分支注册。
    return container
