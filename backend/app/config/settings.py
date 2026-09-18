"""统一配置管理。

为什么这么做：BE-002 的目标是让 SQLite/MySQL、Milvus、Ollama/GLM/DeepSeek
等 Provider 全部通过配置切换，业务代码不出现任何具体实现的名字；
用 pydantic-settings 统一读取环境变量与 .env，同时获得类型校验，
避免错误配置在运行中段才暴露。
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根锚点：backend/ 目录（本文件位于 backend/app/config/）。
# 为什么需要锚定：sqlite 的路径默认是相对路径，若直接按
# 进程工作目录解析，启动方式不同（如在仓库根启动）会把数据写到
# 错误位置；统一锚定到 backend/ 保证数据位置只由配置决定。
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _anchor_path(value: str) -> str:
    """相对路径锚定到 backend/ 目录，绝对路径原样返回。"""
    path = Path(value)
    return str(path if path.is_absolute() else (_PROJECT_ROOT / path))


class DbProvider(str, Enum):
    """数据库 Provider 枚举。

    为什么用枚举：防止拼写错误的配置值静默生效，
    非法值会在应用启动时立即被 pydantic 拒绝。
    """

    SQLITE = "sqlite"
    MYSQL = "mysql"


class VectorStoreProvider(str, Enum):
    """向量数据库 Provider 枚举。

    BE-029 起向量库为 Milvus（稠密 + 稀疏 BM25 混合检索）；
    Chroma 已随迁移删除，枚举保留仅为未来扩展 Provider 预留。
    """

    MILVUS = "milvus"


class MilvusProvider(str, Enum):
    """Milvus 部署形态选择。"""

    CLOUD = "cloud"
    LOCAL = "local"


class LlmProvider(str, Enum):
    """大模型 Provider 枚举。"""

    OLLAMA = "ollama"
    GLM = "glm"
    DEEPSEEK = "deepseek"


class PlannerProvider(str, Enum):
    """规划器 Provider 枚举（BE-030）。

    FOLLOW 表示跟随 LLM_PROVIDER 使用同一个模型实例；
    任务分解对模型能力最敏感，本地小模型规划质量不稳，
    可显式指定 glm 用强模型规划、本地模型执行。
    """

    FOLLOW = "follow"
    OLLAMA = "ollama"
    GLM = "glm"
    DEEPSEEK = "deepseek"


class Settings(BaseSettings):
    """应用运行配置。

    所有字段都可以通过同名环境变量或 backend/.env 覆盖；
    敏感字段（GLM_API_KEY、DEEPSEEK_API_KEY）没有默认值之外的持久化来源，只从环境注入。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # 云端字段使用显式别名，但测试和代码仍可用 Python 字段名传入。
        populate_by_name=True,
        # 额外参数视为配置错误而不是静默忽略，尽早暴露拼写问题
        extra="ignore",
    )

    # ---- 服务基础配置 ----
    host: str = "0.0.0.0"
    port: int = 8000
    # 日志等级默认 INFO：保证"重要业务事件"默认可见（见 docs/RELIABILITY.md）
    log_level: str = "INFO"

    # ---- 日志落盘（RELIABILITY.md：stdout + backend/log 双 sink）----
    log_dir: str = "log"
    log_file_name: str = "app.log"
    log_backup_count: int = 30  # 按天轮转，保留最近 30 天

    # ---- 数据库 Provider ----
    db_provider: DbProvider = DbProvider.SQLITE
    sqlite_db_path: str = "data/law_agent.db"
    mysql_url: str = ""  # 仅 db_provider=mysql 时使用

    # ---- 向量数据库 Provider（Milvus 默认，部署形态独立选择）----
    vector_store_provider: VectorStoreProvider = VectorStoreProvider.MILVUS
    # 默认云端；本地 standalone 必须显式设置 MILVUS_PROVIDER=local，
    # 避免因某一组 URI 缺失而意外连错部署环境。
    milvus_provider: MilvusProvider = MilvusProvider.CLOUD
    milvus_cloud_uri: str = ""
    milvus_cloud_token: str = ""
    milvus_uri: str = "http://127.0.0.1:19530"
    milvus_token: str = ""
    # 业务默认集合与评测集合通过配置隔离，避免评测清理正式知识库。
    milvus_collection_name: str = "law_chunks"

    # ---- 大模型 Provider ----
    llm_provider: LlmProvider = LlmProvider.OLLAMA
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:4b"
    # 向量化模型独立配置：embedding 模型与对话模型通常是不同的模型
    ollama_embedding_model: str = "nomic-embed-text:latest"
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    glm_model: str = "glm-4-flash"
    # 敏感配置：只通过环境变量注入，禁止写入任何文件或日志
    glm_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    # 敏感配置：只通过环境变量注入，禁止写入任何文件或日志
    deepseek_api_key: str = ""
    # 思考模式开关：qwen3.5/glm-4.5 等推理模型默认会先"思考"再回答，
    # 显著拉长首字延迟（真实环境曾达 30~40s）；默认关闭以获得即时流式输出
    llm_enable_thinking: bool = False

    # ---- 规划器 Provider（BE-030 统一规划工作流）----
    # 规划节点把问题拆解为子查询，对模型能力最敏感；
    # follow=复用主 LLM Provider 实例，ollama/glm/deepseek=按所选 Provider 的
    # 连接配置构造独立实例（模型名可用 planner_model 单独覆盖）
    planner_provider: PlannerProvider = PlannerProvider.FOLLOW
    planner_model: str = ""  # 空串表示用所选 Provider 的默认对话模型

    # ---- RAG 评测 Judge（BE-049）----
    # follow 且模型名为空时复用主 LLM；填写模型名或显式选择 Provider
    # 时构造独立 Judge，避免把评测逻辑写进问答工作流。
    eval_judge_provider: PlannerProvider = PlannerProvider.FOLLOW
    eval_judge_model: str = ""

    # ---- Agent 服务（一期重写 BE-033）----
    # Rerank 总开关：默认开启（设计 §32 统一重排）。如果部署环境暂时
    # 不需要精排，可置 false 使用 RRF；服务仍会把“主动关闭”单独记录。
    rerank_enabled: bool = True
    # Rerank 模型与 scripts/check_rerank_model/check_rerank_local.py 保持一致：
    # 默认使用 Hugging Face 模型 id；也可改为脚本下载后的本地快照路径。
    # 加载失败时检索降级为 RRF 融合序，不阻断问答。
    reranker_model_path: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_device: str = "cpu"

    # ---- Langfuse 链路追踪（BE-043）----
    # 总开关：默认关闭——关闭时 langfuse 模块零导入、零开销，纯本地运行；
    # 开启但密钥缺失时装配点 WARN 降级为关闭（可观测故障不阻断业务）。
    langfuse_enabled: bool = False
    # Langfuse 服务地址：云版或自托管实例（如 http://localhost:3000）；
    # 变量名与 langfuse SDK 自身的 LANGFUSE_BASE_URL 口径一致
    langfuse_base_url: str = "https://cloud.langfuse.com"
    # 项目密钥：敏感配置，只经 .env/环境变量注入，禁止提交仓库与写入日志
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    # ---- Tavily Remote MCP 联网搜索 ----
    # 联网是否触发由每次 HTTP 请求的 use_web_search 决定，
    # 这里不再增加全局 WEB_SEARCH_ENABLED，避免配置与前端按钮状态漂移。
    tavily_mcp_url: str = "https://mcp.tavily.com/mcp/"
    # 敏感配置只从环境变量或 backend/.env 注入，任何日志都不得记录其值。
    tavily_api_key: str = ""
    tavily_search_depth: str = "basic"
    tavily_max_results: int = Field(default=5, ge=5, le=20)

    @property
    def resolved_sqlite_db_path(self) -> str:
        """SQLite 数据库文件的实际路径（相对路径锚定到 backend/）。"""
        return _anchor_path(self.sqlite_db_path)

    @property
    def resolved_log_dir(self) -> str:
        """日志目录的实际路径（相对路径锚定到 backend/）。"""
        return _anchor_path(self.log_dir)

    @property
    def resolved_milvus_uri(self) -> str:
        """返回 MILVUS_PROVIDER 选择后的 Endpoint。"""
        return self.milvus_cloud_uri if self.milvus_provider is MilvusProvider.CLOUD else self.milvus_uri

    @property
    def resolved_milvus_token(self) -> str:
        """返回 MILVUS_PROVIDER 选择后的认证 token。"""
        return self.milvus_cloud_token if self.milvus_provider is MilvusProvider.CLOUD else self.milvus_token


@lru_cache
def get_settings() -> Settings:
    """返回全局唯一 Settings 实例。

    为什么用 lru_cache 单例：配置在进程生命周期内不变，
    缓存后各处拿到的是同一份配置，避免重复解析环境变量；
    测试中需要覆盖配置时应直接构造 Settings 实例而不是走此缓存。
    """
    return Settings()
