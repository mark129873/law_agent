"""应用级依赖装配点。

为什么全应用只有一个装配点：所有"抽象接口 -> 具体实现"的映射
集中在此处，切换 Provider 时只改配置与这里的工厂注册，
业务代码与分层结构完全不动，依赖关系一目了然。
"""

from __future__ import annotations

from typing import Callable

from app.agent import create_qa_workflow
from app.agent.config import AgentConfig
from app.agent.services.reranker_service import CrossEncoderScorer, RerankerService
from app.agent.subgraphs.legal_rag.config import LegalRAGConfig
from app.application.services.chat_service import ChatService
from app.application.services.conversation_service import ConversationService
from app.application.services.document_pipeline import DocumentParserFactory, DocumentPipeline
from app.application.services.document_service import DocumentService
from app.application.services.knowledge_service import KnowledgeIngestionService
from app.application.services.rag_service import RagService
from app.common.di import DIContainer
from app.config.settings import PlannerProvider, Settings, VectorStoreProvider, get_settings
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.repositories.vector_store import VectorStore
from app.domain.services.embedding import EmbeddingService
from app.domain.services.qa_workflow import QaWorkflow
from app.domain.services.trace_sink import TraceSink
from app.domain.services.web_search import WebSearchPort
from app.domain.repositories.database import Database
from app.infrastructure.database.sqlalchemy.database import SQLAlchemyDatabase, sqlite_url
from app.infrastructure.document_parser.pdf_parser import PdfParser
from app.infrastructure.document_parser.text_parser import TextParser
from app.infrastructure.embedding.ollama_embedding import OllamaEmbeddingService
from app.infrastructure.llm.glm import GLMProvider
from app.infrastructure.llm.ollama import OllamaProvider
from app.infrastructure.trace.langfuse_sink import LangfuseTraceSinkFactory
from app.infrastructure.vector_store.milvus import MilvusVectorStore
from app.infrastructure.web_search.log_writer import WebSearchLogWriter
from app.infrastructure.web_search.tavily_mcp import TavilyMcpSearchClient


def _build_database(settings: Settings) -> Database:
    """按配置构造数据库实现（工厂函数）。

    为什么在工厂里分支：新增 MySQL 支持时只需在此增加 URL 分支
    （SQLAlchemy 实现本身方言无关，无需新增实现类）。

    注意：mysql 分支目前仍然显式拒绝而不是静默降级——
    没有真实 MySQL 实例验证过的路径不允许被配置启用。
    """
    if settings.db_provider.value == "sqlite":
        # 使用锚定后的绝对路径，避免进程工作目录影响数据位置
        return SQLAlchemyDatabase(sqlite_url(settings.resolved_sqlite_db_path))
    # MySQL 接入只剩"异步驱动 + URL 映射"（见 ARCHITECTURE.md 第 10 节）
    raise NotImplementedError(
        f"数据库 Provider '{settings.db_provider.value}' 尚未实现；"
        f"当前可用：sqlite（SQLAlchemy 实现已就绪，接入 MySQL 需安装 aiomysql 驱动并补真实实例验证）"
    )


def _build_vector_store(settings: Settings) -> VectorStore:
    """按配置构造向量库实现（工厂函数，BE-029）。

    为什么工厂仍然保留：未来接入其他向量库 Provider 时只需在此
    增加分支，业务代码与分层结构不动。

    dense_top_k / bm25_top_k / rrf_k 从 LegalRAGConfig 读取：这三个
    参数本质上是检索业务参数（召回量 + 融合平滑），由业务配置统一定义，
    向量库实现只负责透传到底层 Milvus API。
    """
    if settings.vector_store_provider == VectorStoreProvider.MILVUS:
        rag_cfg = LegalRAGConfig()
        return MilvusVectorStore(
            settings.milvus_uri,
            collection_name=settings.milvus_collection_name,
            dense_top_k=rag_cfg.dense_top_k,
            bm25_top_k=rag_cfg.bm25_top_k,
            rrf_k=rag_cfg.rrf_k,
        )
    raise NotImplementedError(f"向量库 Provider '{settings.vector_store_provider.value}' 尚未实现")


def _build_llm_provider(settings: Settings) -> LLMProvider:
    """按配置构造大模型 Provider（工厂函数，BE-010）。"""
    provider = settings.llm_provider.value
    model = settings.ollama_model if provider == "ollama" else settings.glm_model
    return _build_named_llm_provider(settings, provider, model)


def _build_named_llm_provider(settings: Settings, provider: str, model: str) -> LLMProvider:
    """按 Provider 名称构造模型，供主模型和评测 Judge 共用。"""
    if provider == "ollama":
        return OllamaProvider(settings.ollama_base_url, model, settings.llm_enable_thinking)
    if provider == "glm":
        if not settings.glm_api_key:
            # 密钥缺失时尽早失败，而不是等到第一次请求才报 401
            raise ValueError("模型 Provider=glm 但未配置 GLM_API_KEY 环境变量")
        return GLMProvider(
            settings.glm_base_url, settings.glm_api_key, model, settings.llm_enable_thinking
        )
    raise NotImplementedError(f"大模型 Provider '{provider}' 尚未实现")


def build_evaluation_judge_provider(settings: Settings, primary: LLMProvider) -> LLMProvider:
    """构造评测 Judge；默认复用主模型，显式配置后才建立独立模型。"""
    if settings.eval_judge_provider == PlannerProvider.FOLLOW and not settings.eval_judge_model:
        return primary
    provider = settings.llm_provider.value if settings.eval_judge_provider == PlannerProvider.FOLLOW else settings.eval_judge_provider.value
    default_model = settings.ollama_model if provider == "ollama" else settings.glm_model
    return _build_named_llm_provider(settings, provider, settings.eval_judge_model or default_model)


def _build_planner(settings: Settings, container: DIContainer) -> LLMProvider:
    """按配置构造规划器（工厂函数，BE-030）。

    follow=复用主 LLM Provider 实例（零额外连接）；
    ollama/glm=按主 Provider 的连接配置构造独立实例，
    模型名可用 PLANNER_MODEL 单独覆盖。
    为什么规划器可能用不同模型：任务分解对模型能力最敏感，
    本地小模型规划质量不稳，强模型规划 + 快模型执行是常见组合。
    """
    if settings.planner_provider == PlannerProvider.FOLLOW:
        return container.resolve(LLMProvider)
    model = settings.planner_model  # 空串由各分支回退到该 Provider 默认模型
    if settings.planner_provider == PlannerProvider.OLLAMA:
        return OllamaProvider(settings.ollama_base_url, model or settings.ollama_model, settings.llm_enable_thinking)
    if settings.planner_provider == PlannerProvider.GLM:
        if not settings.glm_api_key:
            raise ValueError("PLANNER_PROVIDER=glm 但未配置 GLM_API_KEY 环境变量")
        return GLMProvider(settings.glm_base_url, settings.glm_api_key, model or settings.glm_model, settings.llm_enable_thinking)
    raise NotImplementedError(f"规划器 Provider '{settings.planner_provider.value}' 尚未实现")


def _build_document_pipeline(settings: Settings) -> DocumentPipeline:
    """构造文档处理 Pipeline：注册全部已实现的解析器策略。"""
    return DocumentPipeline(
        parser_factory=DocumentParserFactory([TextParser(), PdfParser()]),
    )


def _build_embedding_service(settings: Settings) -> EmbeddingService:
    """按配置构造向量生成服务（当前实现：Ollama）。"""
    return OllamaEmbeddingService(settings.ollama_base_url, settings.ollama_embedding_model)


def _build_reranker(settings: Settings) -> RerankerService:
    """构造统一重排服务（BE-033）。

    为什么构造时不加载模型：CrossEncoderScorer 懒加载——首次 rerank
    才读本地模型，装配阶段零开销；加载失败在检索侧降级 RRF 序。
    RERANK_ENABLED=false 时整体降级（CPU 无 CUDA 部署的可行性开关）。
    """
    return RerankerService(
        CrossEncoderScorer(settings.reranker_model_path, settings.reranker_device),
        enabled=settings.rerank_enabled,
    )


def _build_trace_sink_factory(settings: Settings) -> Callable[[], TraceSink | None] | None:
    """按配置构造 trace 汇工厂（BE-043）。

    关闭（默认）返回 None：ChatService 不构造任何观测实现，langfuse
    模块零导入零开销；开启但缺密钥时工厂内部 WARN 降级为恒 None
    （可观测故障不阻断业务，见 infrastructure/trace/langfuse_sink.py）。
    """
    if not settings.langfuse_enabled:
        return None
    return LangfuseTraceSinkFactory(
        base_url=settings.langfuse_base_url,
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
    )


def _build_web_search(settings: Settings) -> WebSearchPort:
    """构造联网搜索端口的 Tavily Remote MCP 适配器。

    这是依赖注入的唯一基础设施装配点：Agent 只依赖
    ``WebSearchPort``，因此单元测试可以注入 fake，生产环境才会创建
    Tavily 的 Streamable HTTP 客户端。日志目录也在这里统一传入，保证
    搜索结果始终落在与普通结构化日志相同的 backend/log 根目录下。
    """
    return TavilyMcpSearchClient(
        mcp_url=settings.tavily_mcp_url,
        api_key=settings.tavily_api_key,
        search_depth=settings.tavily_search_depth,
        max_results=settings.tavily_max_results,
        log_dir=settings.resolved_log_dir,
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
    # 向量库：Milvus（稠密 + 稀疏 BM25 混合检索，BE-029）
    container.register(VectorStore, lambda c: _build_vector_store(settings), singleton=True)
    # 大模型：按 LLM_PROVIDER 配置注册对应实现（BE-010）
    container.register(LLMProvider, lambda c: _build_llm_provider(settings), singleton=True)
    # 联网搜索：端口与 Tavily Remote MCP 适配器的映射集中在装配层；
    # 未配置 API Key 时仍能启动，实际点击搜索后由适配器返回明确状态。
    container.register(WebSearchPort, lambda c: _build_web_search(settings), singleton=True)
    # 文档处理 Pipeline 与知识库入库服务（BE-011/BE-013）
    container.register(DocumentPipeline, lambda c: _build_document_pipeline(settings), singleton=True)
    container.register(EmbeddingService, lambda c: _build_embedding_service(settings), singleton=True)
    container.register(
        KnowledgeIngestionService,
        lambda c: KnowledgeIngestionService(
            pipeline=c.resolve(DocumentPipeline),
            embedding_service=c.resolve(EmbeddingService),
            vector_store=c.resolve(VectorStore),
        ),
        singleton=True,
    )
    # 业务服务（BE-014/018/019/020/021/029）
    container.register(ConversationService, lambda c: ConversationService(c.resolve(Database)), singleton=True)
    container.register(
        RagService,
        lambda c: RagService(c.resolve(EmbeddingService), c.resolve(VectorStore)),
        singleton=True,
    )
    # 统一重排服务（BE-033：本地 MiniLM CrossEncoder，懒加载）
    container.register(RerankerService, lambda c: _build_reranker(settings), singleton=True)
    # 问答工作流作为领域端口注册，ChatService 与评测器复用同一个装配结果。
    container.register(
        QaWorkflow,
        lambda c: create_qa_workflow(
            c.resolve(LLMProvider),
            embedding=c.resolve(EmbeddingService),
            vector_store=c.resolve(VectorStore),
            planner=_build_planner(settings, c),
            reranker=c.resolve(RerankerService),
            agent_config=AgentConfig(),
            rag_config=LegalRAGConfig(),
            web_search=c.resolve(WebSearchPort),
        ),
        singleton=True,
    )
    container.register(
        DocumentService,
        lambda c: DocumentService(
            database=c.resolve(Database),
            parser_factory=c.resolve(DocumentPipeline).parser_factory,
            ingestion_service=c.resolve(KnowledgeIngestionService),
            vector_store=c.resolve(VectorStore),
        ),
        singleton=True,
    )
    container.register(
        ChatService,
        lambda c: ChatService(
            conversation_service=c.resolve(ConversationService),
            # 与评测器复用同一个领域工作流装配，确保两条入口不会漂移。
            qa_graph=c.resolve(QaWorkflow),
            # Langfuse trace 汇工厂（BE-043）：按 LANGFUSE_ENABLED 注入，关闭为 None
            trace_sink_factory=_build_trace_sink_factory(settings),
        ),
        singleton=True,
    )
    return container
