"""FastAPI 应用入口。

为什么用工厂函数：便于测试中按需构建应用实例（注入临时配置），
也为后续根据配置装配不同 Provider（SQLite/MySQL、Chroma/Milvus 等）留出扩展点。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.routes import chat, conversations, documents
from app.common.logging import setup_logging
from app.config.settings import Settings, get_settings
from app.containers import create_container
from app.domain.repositories.vector_store import VectorStore
from app.infrastructure.database.base import Database

# 启动时初始化结构化 JSON 日志，确保后续所有服务日志格式一致
setup_logging()
logger = logging.getLogger("app.main")


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建 FastAPI 应用实例；允许注入自定义配置供测试使用。"""
    settings = settings or get_settings()
    # 装配依赖注入容器：所有"抽象接口 -> 具体实现"的映射从此处开始
    container = create_container(settings)
    # 预构建 Agent 图并在日志中体现模型配置（图在 ChatService 内注册）

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """应用生命周期：启动建库、关闭释放。

        为什么放在 lifespan：数据库连接必须跟随应用进程生死，
        放在请求处理中会造成连接泄漏或初始化竞态。
        """
        database: Database = container.resolve(Database)
        await database.connect()
        await database.init_schema()
        logger.info(
            "Database initialized",
            extra={"service": "database", "provider": settings.db_provider.value},
        )
        # 向量库随应用一起初始化，保证首次请求前存储就绪
        vector_store: VectorStore = container.resolve(VectorStore)
        await vector_store.initialize()
        logger.info(
            "VectorStore initialized",
            extra={"service": "vector_store", "provider": settings.vector_store_provider.value},
        )
        yield
        await vector_store.close()
        await database.close()
        logger.info("Infrastructure closed", extra={"service": "system"})

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
        lifespan=lifespan,
    )
    # 前端开发服务器跨域访问：本地开发全放开，生产环境应收敛为具体来源
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(conversations.router)
    app.include_router(chat.router)
    app.include_router(documents.router)

    @app.get("/api/health", tags=["system"])
    async def health() -> dict[str, str]:
        """健康检查端点，供启动验证与后续部署探活使用。"""
        logger.info("Health check requested", extra={"service": "system"})
        return {"status": "ok"}

    # 容器挂在 app.state 上，请求处理链路可按需解析依赖
    app.state.container = container
    return app


app = create_app()
