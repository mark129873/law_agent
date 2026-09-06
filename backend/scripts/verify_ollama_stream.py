"""BE-010 真实 Ollama 流式调用验证脚本（统一走 LangGraph 图）。"""

import asyncio
import os

os.chdir(r"C:\Users\nnnnnn\Desktop\law_agent\backend")

from app.common.logging import setup_logging
from app.config.settings import Settings
from app.containers import create_container
from app.agent import create_qa_workflow
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.repositories.vector_store import VectorStore


async def main() -> None:
    setup_logging()
    container = create_container(Settings(_env_file=None))
    llm = container.resolve(LLMProvider)
    rag_store = container.resolve(VectorStore)
    await rag_store.initialize()
    # 与生产一致：问答走 LangGraph 图（无 RAG 的基础工作流）
    graph = create_qa_workflow(llm, rag=None)
    print("model:", llm.model_name)

    async def consume() -> list[str]:
        chunks: list[str] = []
        async for chunk in graph.astream(
            {"question": "用一句话回答：离婚冷静期是多少天？", "history": []},
            stream_mode="custom",
        ):
            chunks.append(chunk)
            if sum(len(c) for c in chunks) > 100:
                break
        return chunks

    pieces = await asyncio.wait_for(consume(), timeout=280)
    print("stream chunks:", len(pieces))
    print("joined:", "".join(pieces)[:120])
    await rag_store.close()


asyncio.run(main())
