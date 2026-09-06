"""BE-013 真实 Ollama embedding 端到端验证脚本（临时使用）。

真实链路：DocumentPipeline → OllamaEmbeddingService(nomic-embed-text) → 真实 Chroma
"""
import asyncio
import os
import tempfile

os.chdir(r"C:\Users\nnnnnn\Desktop\law_agent\backend")

from app.common.logging import setup_logging
from app.config.settings import Settings
from app.containers import create_container
from app.application.services.knowledge_service import KnowledgeIngestionService
from app.domain.services.embedding import EmbeddingService
from app.domain.repositories.vector_store import VectorStore
from app.application.services.document_pipeline import DocumentPipeline

setup_logging()


async def main() -> None:
    container = create_container(Settings(_env_file=None))
    pipeline = container.resolve(DocumentPipeline)
    embedding = container.resolve(EmbeddingService)

    # 使用真实持久化目录（临时），模拟一次真实上传入库；
    # ignore_cleanup_errors：Windows 下 chromadb 进程会短暂持有 sqlite 文件锁，
    # 不影响验证本身
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        from app.infrastructure.vector_store.chroma import ChromaVectorStore

        store = ChromaVectorStore(tmp)
        await store.initialize()
        service = KnowledgeIngestionService(pipeline, embedding, store)

        content = (
            "劳动合同违约金条款：劳动者违反服务期约定的，应当按照约定向用人单位支付违约金。"
            "劳动报酬规定：工资应当以货币形式按月支付给劳动者本人，不得克扣或者无故拖欠。"
            "经济补偿条款：用人单位依照本法规定解除劳动合同的，应当向劳动者支付经济补偿。"
        ).encode("utf-8")

        chunk_ids = await service.ingest_document("doc-real-1", "劳动法问答.txt", content)
        print("ingested chunks:", len(chunk_ids))

        # 语义检索：用非原句的问法查询"违约金"相关内容
        query_vector = await embedding.embed_query("员工离职时公司要求赔偿怎么算")
        results = await store.search(query_vector, top_k=3)
        for r in results:
            print(f"score={r.score:.4f} file={r.chunk.metadata.get('filename')} content={r.chunk.content[:40]}...")
        assert results, "检索无结果"
        assert any("违约金" in r.chunk.content for r in results), "未命中违约金相关内容"
        await store.close()
    print("REAL EMBEDDING E2E: PASS")


asyncio.run(main())
