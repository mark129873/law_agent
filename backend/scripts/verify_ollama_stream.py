"""BE-010 真实 Ollama 流式调用验证脚本（统一走 LangGraph 图；BE-038 适配一期主图）。"""

import asyncio
import os

os.chdir(r"C:\Users\nnnnnn\Desktop\law_agent\backend")

from app.common.logging import setup_logging
from app.config.settings import Settings
from app.containers import create_container
from app.agent import create_qa_workflow
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.repositories.vector_store import VectorStore
from app.domain.services.embedding import EmbeddingService


async def main() -> None:
    setup_logging()
    container = create_container(Settings(_env_file=None))
    llm = container.resolve(LLMProvider)
    vector_store = container.resolve(VectorStore)
    await vector_store.initialize()
    # 一期主图：依赖端口组合（LLM + Embedding + VectorStore），planner 跟随主 LLM
    # （本脚本验证流式输出本身，不依赖知识库内容——空库走"信息不足"策略）
    graph = create_qa_workflow(
        llm,
        embedding=container.resolve(EmbeddingService),
        vector_store=vector_store,
    )
    print("model:", llm.model_name)

    async def consume() -> list[str]:
        chunks: list[str] = []
        async for event in graph.astream(
            {"question": "用一句话回答：离婚冷静期是多少天？", "history": []},
            stream_mode="custom",
        ):
            if event.type == "delta":
                chunks.append(event.content)
            if sum(len(c) for c in chunks) > 100:
                break
        return chunks

    pieces = await asyncio.wait_for(consume(), timeout=280)
    print("stream chunks:", len(pieces))
    print("joined:", "".join(pieces)[:120])
    await vector_store.close()


asyncio.run(main())
