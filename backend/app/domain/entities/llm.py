"""LLM 调用相关领域实体。

DDD 说明：ChatMessage 复用 MessageRole 而非另建枚举，体现"通用语言"——
对话消息与大模型请求消息在业务上是同一个概念，两套类型会制造翻译层；
LlmParams 把采样参数收拢为参数对象（Parameter Object 模式），
新增参数不破坏端口方法签名。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.entities.message import MessageRole


@dataclass
class ChatMessage:
    """发给大模型的对话消息。

    为什么复用 MessageRole 而不是新建枚举：对话消息与 LLM 请求消息
    的角色语义完全一致，两套枚举反而需要维护映射关系。
    """

    role: MessageRole
    content: str


@dataclass
class LlmParams:
    """模型调用参数。

    为什么收拢为对象而不是散参数：新增参数（top_p、stop 等）时
    只改本类与具体实现，Provider 接口签名保持稳定。
    """

    temperature: float = 0.7
    max_tokens: int | None = None
