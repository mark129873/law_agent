"""应用级依赖装配点。

为什么全应用只有一个装配点：所有"抽象接口 -> 具体实现"的映射
集中在此处，切换 Provider 时只改配置与这里的工厂注册，
业务代码与分层结构完全不动，依赖关系一目了然。
"""

from __future__ import annotations

from app.agent import create_qa_workflow
from app.application.services.chat_service import ChatService
from app.application.services.conversation_service import ConversationService
from app.application.services.document_pipeline import DocumentParserFactory, DocumentPipeline
from app.application.services.document_service import DocumentService
from app.application.services.knowledge_service import KnowledgeIngestionService
from app.application.services.rag_service import RagService
from app.common.di import DIContainer
from app.config.settings import Settings, get_settings
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.repositories.vector_store import VectorStore
from app.domain.services.embedding import EmbeddingService
from app.domain.repositories.database import Database
from app.infrastructure.database.sqlalchemy.database import SQLAlchemyDatabase, sqlite_url
from app.infrastructure.document_parser.pdf_parser import PdfParser
from app.infrastructure.document_parser.text_parser import TextParser
from app.infrastructure.embedding.ollama_embedding import OllamaEmbeddingService
from app.infrastructure.llm.glm import GLMProvider
from app.infrastructure.llm.ollama import OllamaProvider
from app.infrastructure.vector_store.chroma import ChromaVectorStore
from app.infrastructure.vector_store.milvus import MilvusVectorStore


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
    """按配置构造向量库实现（工厂函数，BE-008）。

    为什么骨架也纳入工厂：VECTOR_STORE_PROVIDER=milvus 时装配成功、
    使用时才报"未实现"，这样 Provider 的表达能力与 Chroma 完全一致，
    未来 Milvus 落地只改本函数的一行分支。
    """
    if settings.vector_store_provider.value == "chroma":
        # 使用锚定后的绝对路径，避免进程工作目录影响数据位置
        return ChromaVectorStore(settings.resolved_chroma_persist_dir)
    if settings.vector_store_provider.value == "milvus":
        return MilvusVectorStore(settings.milvus_uri)
    raise NotImplementedError(f"向量库 Provider '{settings.vector_store_provider.value}' 尚未实现")


def _build_llm_provider(settings: Settings) -> LLMProvider:
    """按配置构造大模型 Provider（工厂函数，BE-010）。"""
    if settings.llm_provider.value == "ollama":
        return OllamaProvider(settings.ollama_base_url, settings.ollama_model, settings.llm_enable_thinking)
    if settings.llm_provider.value == "glm":
        if not settings.glm_api_key:
            # 密钥缺失时尽早失败，而不是等到第一次请求才报 401
            raise ValueError("LLM_PROVIDER=glm 但未配置 GLM_API_KEY 环境变量")
        return GLMProvider(
            settings.glm_base_url, settings.glm_api_key, settings.glm_model, settings.llm_enable_thinking
        )
    raise NotImplementedError(f"大模型 Provider '{settings.llm_provider.value}' 尚未实现")


def _build_document_pipeline(settings: Settings) -> DocumentPipeline:
    """构造文档处理 Pipeline：注册全部已实现的解析器策略。"""
    return DocumentPipeline(
        parser_factory=DocumentParserFactory([TextParser(), PdfParser()]),
    )


def _build_embedding_service(settings: Settings) -> EmbeddingService:
    """按配置构造向量生成服务（当前实现：Ollama）。"""
    return OllamaEmbeddingService(settings.ollama_base_url, settings.ollama_embedding_model)


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
    # 业务服务（BE-014/018/019/020/021）
    container.register(ConversationService, lambda c: ConversationService(c.resolve(Database)), singleton=True)
    container.register(RagService, lambda c: RagService(c.resolve(EmbeddingService), c.resolve(VectorStore)), singleton=True)
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
            # 唯一的问答执行体：经 agent 包工厂构建，langgraph 类型不外泄
            qa_graph=create_qa_workflow(c.resolve(LLMProvider), rag=c.resolve(RagService)),
        ),
        singleton=True,
    )
    return container
