"""FastAPI 应用入口。

为什么这么做：BE-001 的目标是建立统一的应用入口与模块边界，
本文件只负责创建应用实例、装配日志与暴露健康检查端点；
具体业务路由将在对应功能（BE-019 等）中按分层注册进来。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.common.logging import setup_logging
from app.config.settings import get_settings
from app.containers import create_container

# 启动时初始化结构化 JSON 日志，确保后续所有服务日志格式一致
setup_logging()
logger = logging.getLogger("app.main")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。

    为什么用工厂函数：便于测试中按需构建应用实例，
    也为后续根据配置装配不同 Provider（SQLite/MySQL、Chroma/Milvus 等）留出扩展点。
    """
    settings = get_settings()
    # 装配依赖注入容器：所有"抽象接口 -> 具体实现"的映射从此处开始
    container = create_container(settings)
    # 启动即记录当前生效的 Provider，方便从日志确认配置是否按预期切换；
    # 注意：只输出 Provider 名称等非敏感信息，密钥一律不进日志。
    logger.info(
        "Application configured",
        extra={
            "service": "system",
            "db_provider": settings.db_provider.value,
            "vector_store_provider": settings.vector_store_provider.value,
            "llm_provider": settings.llm_provider.value,
        },
    )

    app = FastAPI(
        title="Legal Knowledge Agent",
        description="法律知识库与法律问答 Agent 后端服务",
        version="0.1.0",
    )
    # 容器挂在 app.state 上，请求处理链路可按需解析依赖
    app.state.container = container

    @app.get("/api/health", tags=["system"])
    async def health() -> dict[str, str]:
        """健康检查端点，供启动验证与后续部署探活使用。"""
        logger.info("Health check requested", extra={"service": "system"})
        return {"status": "ok"}

    return app


app = create_app()
