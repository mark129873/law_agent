"""LLMProvider 抽象接口。

为什么接口放在 domain 层：Agent 与问答服务依赖的是"一个能对话的模型"
这一领域契约，Ollama/GLM 只是实现；这是 LangGraph 工作流不绑定
具体厂商的前提（依赖倒置）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from app.domain.entities.llm import ChatMessage, LlmParams


class LLMProvider(ABC):
    """大模型 Provider 契约。"""

    @abstractmethod
    async def chat(self, messages: list[ChatMessage], params: LlmParams | None = None) -> str:
        """同步问答：返回完整回答文本。"""

    @abstractmethod
    def stream(self, messages: list[ChatMessage], params: LlmParams | None = None) -> AsyncIterator[str]:
        """流式问答：按增量 token 产出回答片段。

        为什么定义为普通方法返回 AsyncIterator 而不是 async def：
        async def 生成器需要 await 后才能拿迭代器，调用方书写繁琐；
        普通方法直接返回异步迭代器，`async for chunk in provider.stream(...)` 即用。
        """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """当前使用的模型名称，用于日志与前端展示（不含密钥）。"""
