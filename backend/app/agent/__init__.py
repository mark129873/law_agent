"""Agent 模块：一期重写后的问答工作流唯一实现位置。

为什么独立成模块：本模块是全项目唯一允许导入 langgraph 与重型推理库
（sentence_transformers/torch）的业务模块（DDD 边界守护测试锁定），
它把领域端口（LLMProvider/EmbeddingService/VectorStore）装配到
LangGraph 主图 + Local Legal RAG 子图上（设计 §3/§4），其余模块只应
通过本包暴露的 create_qa_workflow 工厂使用工作流。

架构说明见 docs/adr/0001~0007，设计依据 legal_agent_phase1_technical_design.md。
"""

from __future__ import annotations

from app.agent.config import AgentConfig
from app.agent.graph import AgentGraphBuilder, LangGraphQaWorkflow
from app.agent.services.llm_service import LLMService
from app.agent.services.milvus_service import MilvusService
from app.agent.services.reranker_service import CrossEncoderScorer, RerankerService
from app.agent.subgraphs.legal_rag.config import LegalRAGConfig
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.repositories.vector_store import VectorStore
from app.domain.services.embedding import EmbeddingService
from app.domain.services.qa_workflow import QaWorkflow


def _default_reranker() -> RerankerService:
    """缺省 reranker：按全局配置加载本地 CrossEncoder（懒加载，不触模型）。"""
    from app.config.settings import get_settings

    settings = get_settings()
    return RerankerService(CrossEncoderScorer(settings.reranker_model_path, settings.reranker_device))


def create_qa_workflow(
    llm: LLMProvider,
    embedding: EmbeddingService,
    vector_store: VectorStore,
    planner: LLMProvider | None = None,
    reranker: RerankerService | None = None,
    agent_config: AgentConfig | None = None,
    rag_config: LegalRAGConfig | None = None,
) -> QaWorkflow:
    """构建一期 Agent 工作流（主图 + Local Legal RAG 子图）。

    为什么返回类型标注为端口：调用方（装配点）只需知道拿到的是
    QaWorkflow 实现，LangGraph 与建造细节被封禁在本模块内部。
    依赖全部显式注入：planner 缺省跟随主 LLM（BE-030 约定延续），
    reranker 缺省按全局配置构造本地 CrossEncoder（懒加载，加载失败
    自动降级 RRF 序，ADR-0004）。
    """
    return LangGraphQaWorkflow(
        AgentGraphBuilder(
            llm=LLMService(llm),
            planner=LLMService(planner or llm),
            milvus=MilvusService(embedding, vector_store),
            reranker=reranker or _default_reranker(),
            agent_config=agent_config,
            rag_config=rag_config,
        ).build()
    )
