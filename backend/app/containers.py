"""应用级依赖装配点。

为什么全应用只有一个装配点：所有"抽象接口 -> 具体实现"的映射
集中在此处，切换 Provider 时只改配置与这里的工厂注册，
业务代码与分层结构完全不动，依赖关系一目了然。
"""

from __future__ import annotations

from app.common.di import DIContainer
from app.config.settings import Settings, get_settings
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.repositories.vector_store import VectorStore
from app.infrastructure.database.base import Database
from app.infrastructure.database.sqlite.database import SQLiteDatabase
from app.infrastructure.llm.glm import GLMProvider
from app.infrastructure.llm.ollama import OllamaProvider
from app.infrastructure.vector_store.chroma import ChromaVectorStore
from app.infrastructure.vector_store.milvus import MilvusVectorStore


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


def _build_vector_store(settings: Settings) -> VectorStore:
    """按配置构造向量库实现（工厂函数，BE-008）。

    为什么骨架也纳入工厂：VECTOR_STORE_PROVIDER=milvus 时装配成功、
    使用时才报"未实现"，这样 Provider 的表达能力与 Chroma 完全一致，
    未来 Milvus 落地只改本函数的一行分支。
    """
    if settings.vector_store_provider.value == "chroma":
        return ChromaVectorStore(settings.chroma_persist_dir)
    if settings.vector_store_provider.value == "milvus":
        return MilvusVectorStore(settings.milvus_uri)
    raise NotImplementedError(f"向量库 Provider '{settings.vector_store_provider.value}' 尚未实现")


def _build_llm_provider(settings: Settings) -> LLMProvider:
    """按配置构造大模型 Provider（工厂函数，BE-010）。"""
    if settings.llm_provider.value == "ollama":
        return OllamaProvider(settings.ollama_base_url, settings.ollama_model)
    if settings.llm_provider.value == "glm":
        if not settings.glm_api_key:
            # 密钥缺失时尽早失败，而不是等到第一次请求才报 401
            raise ValueError("LLM_PROVIDER=glm 但未配置 GLM_API_KEY 环境变量")
        return GLMProvider(settings.glm_base_url, settings.glm_api_key, settings.glm_model)
    raise NotImplementedError(f"大模型 Provider '{settings.llm_provider.value}' 尚未实现")


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
    # 向量库：按 VECTOR_STORE_PROVIDER 配置注册对应实现（BE-006~008）
    container.register(VectorStore, lambda c: _build_vector_store(settings), singleton=True)
    # 大模型：按 LLM_PROVIDER 配置注册对应实现（BE-010）
    container.register(LLMProvider, lambda c: _build_llm_provider(settings), singleton=True)
    return container
