"""Agent 模块：问答工作流的唯一实现位置。

为什么独立成模块：本模块是全项目唯一允许导入 langgraph 的业务模块，
它把领域端口（LLMProvider）与应用服务（RagService）装配到 LangGraph
引擎上，实现 QaWorkflow 领域端口；其余模块只应通过本包暴露的
create_qa_workflow 工厂使用工作流，不感知 LangGraph 的存在。
"""

from __future__ import annotations

from app.domain.repositories.llm_provider import LLMProvider
from app.domain.services.qa_workflow import QaWorkflow


def create_qa_workflow(llm: LLMProvider, rag=None) -> QaWorkflow:
    """构建问答工作流（rag 为 None 时为基础工作流，无知识库检索）。

    为什么返回类型标注为端口而不是 CompiledStateGraph：
    调用方（装配点）只需知道拿到的是 QaWorkflow 实现，
    LangGraph 类型被封禁在本模块内部。
    """
    # 延迟导入：把 langgraph 相关符号保持在 agent 包内部
    from app.agent.graph import build_qa_graph

    return build_qa_graph(llm, rag=rag)
