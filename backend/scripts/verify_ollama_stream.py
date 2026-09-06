"""BE-010 真实 Ollama 流式调用验证脚本（临时使用）。"""

import asyncio
import os

os.chdir(r"C:\Users\nnnnnn\Desktop\law_agent\backend")

from app.common.logging import setup_logging
from app.config.settings import Settings
from app.containers import create_container
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.entities.llm import ChatMessage
from app.domain.entities.message import MessageRole


async def main() -> None:
    setup_logging()
    container = create_container(Settings(_env_file=None))
    provider: LLMProvider = container.resolve(LLMProvider)
    print("model:", provider.model_name)
    messages = [ChatMessage(role=MessageRole.USER, content="用一句话回答：离婚冷静期是多少天？")]

    async def consume() -> list[str]:
        chunks: list[str] = []
        async for chunk in provider.stream(messages):
            chunks.append(chunk)
            if sum(len(c) for c in chunks) > 100:
                break
        return chunks

    pieces = await asyncio.wait_for(consume(), timeout=120)
    print("stream chunks:", len(pieces))
    print("joined:", "".join(pieces)[:120])


asyncio.run(main())
