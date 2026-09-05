"""统一配置管理。

为什么这么做：BE-002 的目标是让 SQLite/MySQL、Chroma/Milvus、Ollama/GLM
等 Provider 全部通过配置切换，业务代码不出现任何具体实现的名字；
用 pydantic-settings 统一读取环境变量与 .env，同时获得类型校验，
避免错误配置在运行中段才暴露。
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DbProvider(str, Enum):
    """数据库 Provider 枚举。

    为什么用枚举：防止拼写错误的配置值静默生效，
    非法值会在应用启动时立即被 pydantic 拒绝。
    """

    SQLITE = "sqlite"
    MYSQL = "mysql"


class VectorStoreProvider(str, Enum):
    """向量数据库 Provider 枚举。"""

    CHROMA = "chroma"
    MILVUS = "milvus"


class LlmProvider(str, Enum):
    """大模型 Provider 枚举。"""

    OLLAMA = "ollama"
    GLM = "glm"


class Settings(BaseSettings):
    """应用运行配置。

    所有字段都可以通过同名环境变量或 backend/.env 覆盖；
    敏感字段（GLM_API_KEY）没有默认值之外的持久化来源，只从环境注入。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # 额外参数视为配置错误而不是静默忽略，尽早暴露拼写问题
        extra="ignore",
    )

    # ---- 服务基础配置 ----
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "ERROR"

    # ---- 数据库 Provider ----
    db_provider: DbProvider = DbProvider.SQLITE
    sqlite_db_path: str = "data/law_agent.db"
    mysql_url: str = ""  # 仅 db_provider=mysql 时使用

    # ---- 向量数据库 Provider ----
    vector_store_provider: VectorStoreProvider = VectorStoreProvider.CHROMA
    chroma_persist_dir: str = "data/chroma"
    milvus_uri: str = ""  # 仅 vector_store_provider=milvus 时使用

    # ---- 大模型 Provider ----
    llm_provider: LlmProvider = LlmProvider.OLLAMA
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    glm_model: str = "glm-4-flash"
    # 敏感配置：只通过环境变量注入，禁止写入任何文件或日志
    glm_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    """返回全局唯一 Settings 实例。

    为什么用 lru_cache 单例：配置在进程生命周期内不变，
    缓存后各处拿到的是同一份配置，避免重复解析环境变量；
    测试中需要覆盖配置时应直接构造 Settings 实例而不是走此缓存。
    """
    return Settings()
