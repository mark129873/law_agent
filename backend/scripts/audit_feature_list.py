"""feature_list.json 后端部分审计脚本：逐项核对证据声明 vs 仓库事实。

每条检查对应 evidence 中的一句可机械验证的声明：
- 文件/目录存在性
- 关键代码特征（类、函数、常量、关键字符串）
- 测试计数
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(r"C:\Users\nnnnnn\Desktop\law_agent")
BACKEND = ROOT / "backend"
APP = BACKEND / "app"

results: list[tuple[str, str, bool, str]] = []  # (feature, check, ok, detail)


def check(fid: str, label: str, ok: bool, detail: str = "") -> None:
    results.append((fid, label, ok, detail))


def file_has(rel: str, *needles: str) -> bool:
    p = BACKEND / rel
    if not p.is_file():
        return False
    src = p.read_text(encoding="utf-8")
    return all(n in src for n in needles)


def dir_exists(rel: str) -> bool:
    return (BACKEND / rel).is_dir()


def src_has(rel: str, *needles: str) -> bool:
    p = ROOT / rel
    if not p.is_file():
        return False
    src = p.read_text(encoding="utf-8")
    return all(n in src for n in needles)


# BE-001 基础框架
check("BE-001", "create_app 工厂存在", file_has("app/main.py", "def create_app"))
check("BE-001", "lifespan 自动初始化", file_has("app/main.py", "lifespan", "Database initialized"))
check("BE-001", "健康检查端点", file_has("app/main.py", "/api/health"))
check("BE-001", "uv 环境就绪", dir_exists(".venv") and (BACKEND / "uv.lock").is_file())

# BE-002 配置管理
check("BE-002", "统一 Settings + get_settings", file_has("app/config/settings.py", "class Settings", "def get_settings"))
check("BE-002", "三个 Provider 枚举开关", file_has(
    "app/config/settings.py", "class DbProvider", "class VectorStoreProvider", "class LlmProvider"))
check("BE-002", "路径锚定 resolved_*", file_has(
    "app/config/settings.py", "resolved_sqlite_db_path", "resolved_chroma_persist_dir", "_PROJECT_ROOT"))
check("BE-002", "GLM_API_KEY 仅环境注入", file_has("app/config/settings.py", "glm_api_key: str = \"\""))
check("BE-002", ".env.example 模板", (BACKEND / ".env.example").is_file())

# BE-003 分层与 DI
check("BE-003", "DIContainer 存在", file_has("app/common/di.py", "class DIContainer"))
check("BE-003", "唯一装配点", file_has("app/containers.py", "def create_container"))
check("BE-003", "agent 工厂 create_qa_workflow", file_has("app/agent/__init__.py", "def create_qa_workflow"))
check("BE-003", "边界守护测试存在", (BACKEND / "tests/unit/test_ddd_boundaries.py").is_file())

# BE-004 数据库抽象层
check("BE-004", "Database/TransactionContext 端口在 domain", file_has(
    "app/domain/repositories/database.py", "class Database(ABC)", "class TransactionContext(ABC)"))
check("BE-004", "三 Repository 端口", all(
    (APP / "domain/repositories" / n).is_file() for n in ("conversation.py", "message.py", "document.py")))
check("BE-004", "实体契约", all(
    (APP / "domain/entities" / n).is_file() for n in ("conversation.py", "message.py", "document.py")))
check("BE-004", "抽象不在 infrastructure（已迁移）", not (APP / "infrastructure/database/base.py").exists())

# BE-005 SQLite 实现
check("BE-005", "aiosqlite 实现", file_has("app/infrastructure/database/sqlite/database.py", "aiosqlite", "class SQLiteDatabase"))
check("BE-005", "事务深度计数守卫", file_has("app/infrastructure/database/sqlite/database.py", "_tx_depth"))
check("BE-005", "幂等建表", file_has("app/infrastructure/database/sqlite/database.py", "IF NOT EXISTS"))

# BE-006 向量库抽象
check("BE-006", "chunk 契约", file_has("app/domain/entities/chunk.py", "class DocumentChunk", "class RetrievedChunk"))
check("BE-006", "VectorStore 端口", file_has(
    "app/domain/repositories/vector_store.py", "class VectorStore(ABC)", "add_chunks", "delete_by_document"))

# BE-007 Chroma 实现
check("BE-007", "PersistentClient + law_chunks + cosine", file_has(
    "app/infrastructure/vector_store/chroma.py", "PersistentClient", "law_chunks", "cosine"))
check("BE-007", "阻塞调用经 to_thread", file_has("app/infrastructure/vector_store/chroma.py", "asyncio.to_thread"))

# BE-008 Milvus 骨架
check("BE-008", "骨架 + 明确 NotImplemented", file_has(
    "app/infrastructure/vector_store/milvus.py", "class MilvusVectorStore", "NotImplementedError"))

# BE-009 LLM 抽象
check("BE-009", "ChatMessage/LlmParams", file_has("app/domain/entities/llm.py", "class ChatMessage", "class LlmParams"))
check("BE-009", "LLMProvider 端口", file_has(
    "app/domain/repositories/llm_provider.py", "class LLMProvider(ABC)", "async def chat", "def stream", "model_name"))

# BE-010 Ollama/GLM
check("BE-010", "Ollama /api/chat + NDJSON", file_has("app/infrastructure/llm/ollama.py", "/api/chat", "aiter_lines"))
check("BE-010", "GLM OpenAI 兼容 + SSE", file_has(
    "app/infrastructure/llm/glm.py", "chat/completions", "data:", "[DONE]"))
check("BE-010", "glm 缺密钥装配即报错", file_has("app/containers.py", "GLM_API_KEY"))

# BE-011 Pipeline
check("BE-011", "解析器策略接口", file_has(
    "app/domain/services/document_parser.py", "class DocumentParser(ABC)", "UnsupportedFormatError"))
check("BE-011", "段落感知切分", file_has(
    "app/application/services/document_pipeline.py", "def chunk_text", 'split("\\n")'))
check("BE-011", "解析经 to_thread", file_has("app/application/services/document_pipeline.py", "asyncio.to_thread"))

# BE-012 PDF/TXT/MD 解析
check("BE-012", "TextParser 支持 md + 编码回退", file_has(
    "app/infrastructure/document_parser/text_parser.py", ".md", "gb18030"))
check("BE-012", "PdfParser pypdf", file_has(
    "app/infrastructure/document_parser/pdf_parser.py", "pypdf", "extract_text"))
check("BE-012", "真实测试数据存在", all(
    (BACKEND / "tests/data_source" / n).is_file()
    for n in ("中华人民共和国专利法.txt", "中华人民共和国专利法（要点笔记）.md")))

# BE-013 Embedding 与入库
check("BE-013", "EmbeddingService 端口", file_has("app/domain/services/embedding.py", "class EmbeddingService(ABC)"))
check("BE-013", "Ollama /api/embed 批量", file_has(
    "app/infrastructure/embedding/ollama_embedding.py", "/api/embed", "embed_documents"))
check("BE-013", "入库编排服务", file_has(
    "app/application/services/knowledge_service.py", "class KnowledgeIngestionService", "ingest_document"))

# BE-014 RAG 检索
check("BE-014", "retrieve + build_context + min_score", file_has(
    "app/application/services/rag_service.py", "async def retrieve", "async def build_context", "min_score"))
check("BE-014", "来源标注格式", file_has("app/application/services/rag_service.py", "【来源："))

# BE-015/016 Agent 工作流
check("BE-015", "节点命令模式（AgentNode ABC）", file_has(
    "app/agent/nodes.py", "class AgentNode(ABC)", "class RetrieveNode", "class GenerateNode"))
check("BE-015", "建造者 + 适配器", file_has(
    "app/agent/graph.py", "class QaGraphBuilder", "class LangGraphQaWorkflow(QaWorkflow)"))
check("BE-015", "工厂返回端口类型", file_has("app/agent/__init__.py", "-> QaWorkflow"))
check("BE-016", "rag 分支装配 retrieve", file_has("app/agent/graph.py", '"retrieve"', "RetrieveNode"))
check("BE-016", "流式经 stream writer", file_has("app/agent/nodes.py", "get_stream_writer"))

# BE-017 回答策略
check("BE-017", "策略三规则", file_has(
    "app/agent/prompts.py", "LEGAL_SYSTEM_PROMPT", "知识库中暂无相关依据", "严禁虚构"))

# BE-018 对话服务
check("BE-018", "ConversationService + 统一异常", file_has(
    "app/application/services/conversation_service.py", "class ConversationService", "ConversationNotFoundError"))

# BE-019 核心 API
check("BE-019", "三个路由模块", all(
    (APP / "api/routes" / n).is_file() for n in ("conversations.py", "chat.py", "documents.py")))
check("BE-019", "统一错误处理器", file_has(
    "app/api/errors.py", "class AppError", "register_exception_handlers"))

# BE-020 流式 API
# 路由由 prefix="/api/chat" 与 @router.post("/stream") 拼接而成，故分两段核对
check("BE-020", "SSE 流式端点", file_has(
    "app/api/routes/chat.py", 'prefix="/api/chat"', '"/stream"', "text/event-stream"))
check("BE-020", "流式走图（astream custom）", file_has(
    "app/application/services/chat_service.py", 'stream_mode="custom"'))

# BE-021 上传 API
check("BE-021", "格式白名单 + 大小上限", file_has(
    "app/application/services/document_service.py", "get_parser", "_MAX_UPLOAD_SIZE"))
check("BE-021", "状态机 processing→ready/failed", file_has(
    "app/application/services/document_service.py", "DocumentStatus.PROCESSING", "DocumentStatus.READY", "DocumentStatus.FAILED"))

# BE-022 异常处理与测试
check("BE-022", "AppError 错误码体系", file_has(
    "app/api/errors.py", "40401", "40402", "40001", "41301", "40002", "50000"))
check("BE-022", "unit/integration 分层目录", dir_exists("tests/unit") and dir_exists("tests/integration"))
check("BE-022", "三个 E2E 验证脚本", all(
    (BACKEND / "scripts" / n).is_file()
    for n in ("verify_ollama_stream.py", "verify_real_embedding.py", "verify_real_e2e.py")))

# 测试计数核对（从 evidence 声明：37 / 46 / 83）
def pytest_count(args: list[str]) -> int:
    import pytest
    import os
    cwd = os.getcwd()
    os.chdir(BACKEND)
    try:
        class Plugin:
            def __init__(self): self.n = 0
            def pytest_collection_modifyitems(self, items): self.n = len(items)
        plugin = Plugin()
        pytest.main(args + ["-q", "--co", "--no-header"], plugins=[plugin])
        return plugin.n
    finally:
        os.chdir(cwd)

unit_n = pytest_count(["tests/unit"])
integ_n = pytest_count(["tests/integration"])
total_n = pytest_count(["tests"])
check("计数", f"单元=37（实际 {unit_n}）", unit_n == 37)
check("计数", f"集成=46（实际 {integ_n}）", integ_n == 46)
check("计数", f"总计=83（实际 {total_n}）", total_n == 83)

# 状态核对
data = json.load(open(ROOT / "feature_list.json", encoding="utf-8"))
be = [f for f in data["features"] if f["id"].startswith("BE")]
check("状态", "22 项后端全部 passing", all(f["status"] == "passing" for f in be) and len(be) == 22)
check("状态", "前端 10 项全部 planned 未动", all(
    f["status"] == "planned" for f in data["features"] if f["id"].startswith("FE")))

# 输出报告
fails = [r for r in results if not r[2]]
for fid, label, ok, detail in results:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {fid} {label}" + (f" —— {detail}" if detail and not ok else ""))
print(f"\n=== 审计完成：{len(results) - len(fails)}/{len(results)} 项核对通过 ===")
sys.exit(1 if fails else 0)
