"""LangGraph 问答图可视化导出脚本（BE-031，BE-038 适配一期主图）。

做什么：用桩依赖构建 AgentGraphBuilder 的主图（含 Local Legal RAG
子图），导出 Mermaid 文本（默认写入 docs/qa_graph.mmd，同时打印到
stdout）；加 --png 可再导出 PNG 图片（依赖联网访问 mermaid.ink，
失败时给出替代方案提示）。

为什么用桩依赖就能建图：build() 只是把节点实例注册进 StateGraph，
不会执行任何节点——LLM/Embedding/向量库/Reranker 仅需"能被实例化
进构造函数"即可。桩模式让本脚本不依赖 Milvus / Ollama / GLM /
本地 rerank 模型，随时可跑，这也是依赖倒置（DIP）带来的可测试性收益。

怎么查看结果：
- 把 docs/qa_graph.mmd 内容粘到 https://mermaid.live 或 VS Code
  的 Mermaid 预览插件即可看到交互式图；
- GitHub 原生渲染 Markdown 中的 mermaid 代码块，docs/ARCHITECTURE.md
  §5 已内嵌同款图。

用法：cd backend && uv run python scripts/export_qa_graph.py [--png]
"""
import argparse
import os
import sys

# 脚本直跑时 sys.path 只有 scripts/，手动加入 backend/ 才能导入 app 包
# （与 scripts/reset_milvus.py 同一套路径锚定约定）
_BACKEND_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
os.chdir(_BACKEND_ROOT)
sys.path.insert(0, os.path.abspath(_BACKEND_ROOT))

from app.agent.graph import AgentGraphBuilder
from app.agent.services.llm_service import LLMService
from app.agent.services.milvus_service import MilvusService
from app.agent.services.reranker_service import RerankerService
from app.domain.repositories.llm_provider import LLMProvider
from app.domain.repositories.vector_store import VectorStore
from app.domain.services.embedding import EmbeddingService

# 导出文件统一落在仓库根的 docs/ 下，与文档内嵌图保持同源
_REPO_ROOT = os.path.abspath(os.path.join(_BACKEND_ROOT, ".."))
_MMD_PATH = os.path.join(_REPO_ROOT, "docs", "qa_graph.mmd")
_PNG_PATH = os.path.join(_REPO_ROOT, "docs", "qa_graph.png")


class _StubLLM(LLMProvider):
    """LLMProvider 桩：仅供建图实例化节点，图不会真正调用它。"""

    @property
    def model_name(self) -> str:
        return "stub-model"

    async def chat(self, *args, **kwargs):  # pragma: no cover - 不会被调用
        raise RuntimeError("导出图用途的桩 LLM 不应被调用")

    async def stream(self, *args, **kwargs):  # pragma: no cover - 不会被调用
        raise RuntimeError("导出图用途的桩 LLM 不应被调用")
        yield  # noqa: unreachable——使本函数成为异步生成器以匹配端口签名


class _StubEmbedding(EmbeddingService):
    """Embedding 桩：仅供建图实例化检索节点，不会真正向量化。"""

    async def embed_documents(self, texts):  # pragma: no cover - 不会被调用
        raise RuntimeError("导出图用途的桩 Embedding 不应被调用")

    async def embed_query(self, text):  # pragma: no cover - 不会被调用
        raise RuntimeError("导出图用途的桩 Embedding 不应被调用")


class _StubVectorStore(VectorStore):
    """向量库桩：仅供建图实例化检索节点，不会真正连接 Milvus。"""

    async def initialize(self) -> None: ...
    async def close(self) -> None: ...

    async def add_chunks(self, chunks, embeddings):  # pragma: no cover - 不会被调用
        raise RuntimeError("导出图用途的桩向量库不应被调用")

    async def hybrid_search(self, *args, **kwargs):  # pragma: no cover - 不会被调用
        raise RuntimeError("导出图用途的桩向量库不应被调用")

    async def delete_by_document(self, document_id):  # pragma: no cover - 不会被调用
        raise RuntimeError("导出图用途的桩向量库不应被调用")


class _StubScorer:
    """Rerank 打分器桩：仅供建图实例化重排节点，不会加载模型。"""

    async def score(self, query, documents):  # pragma: no cover - 不会被调用
        raise RuntimeError("导出图用途的桩打分器不应被调用")


def build_graph():
    """用桩依赖构建主图（装配逻辑与生产完全一致，仅依赖为桩）。"""
    llm = LLMService(_StubLLM())
    return AgentGraphBuilder(
        llm=llm,
        planner=LLMService(_StubLLM()),
        milvus=MilvusService(_StubEmbedding(), _StubVectorStore()),
        reranker=RerankerService(_StubScorer()),
    ).build()


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 LangGraph 问答图为 Mermaid/PNG")
    parser.add_argument(
        "--png",
        action="store_true",
        help="额外导出 PNG（需联网访问 mermaid.ink）",
    )
    args = parser.parse_args()

    graph = build_graph()

    # draw_mermaid：langgraph 内置的图结构反序列化，输出 Mermaid flowchart 文本；
    # 条件边会带分支标签（replan / generate / regenerate / end）
    mermaid = graph.get_graph().draw_mermaid()

    with open(_MMD_PATH, "w", encoding="utf-8") as f:
        f.write(mermaid + "\n")
    print(mermaid)
    print(f"\nmermaid 已写入: {_MMD_PATH}", file=sys.stderr)

    # PNG 是可选项：draw_mermaid_png 把 Mermaid 文本发给 mermaid.ink 渲染，
    # 离线环境不可用，失败时引导用户改用 mermaid.live 渲染 mmd 文件
    if args.png:
        try:
            png_bytes = graph.get_graph().draw_mermaid_png()
            with open(_PNG_PATH, "wb") as f:
                f.write(png_bytes)
            print(f"png 已写入: {_PNG_PATH}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - 网络失败属于预期路径，给出提示即可
            print(
                f"PNG 导出失败（{exc}）。"
                f"可离线替代：把 {_MMD_PATH} 内容粘贴到 https://mermaid.live 渲染导出。",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
