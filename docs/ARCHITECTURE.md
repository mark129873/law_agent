# Architecture

## 1. 系统概览
本项目是一个法律知识库与法律问答 Agent，采用前后端分离架构：
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                            │
│ React + TypeScript + Vite + Tailwind CSS                   │
│ React Router + Fetch                                       │
│                                                             │
│ Chat / Conversation / Knowledge Base / Document Upload     │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP / SSE
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                         Backend                             │
│ Python 3.11.15 + FastAPI + Async                           │
│                                                             │
│ API Layer                                                  │
│   ↓                                                        │
│ Application Layer                                          │
│   ↓                                                        │
│ Domain Layer                                               │
│   ↓                                                        │
│ Infrastructure Layer                                       │
└───────────────┬─────────────────────┬───────────────────────┘
                │                     │
                ▼                     ▼
        ┌──────────────┐      ┌──────────────────┐
        │ SQL Database │      │ Vector Database  │
        │ SQLite       │      │ Chroma           │
        │ → MySQL      │      │ → Milvus         │
        └──────────────┘      └──────────────────┘
                │
                ▼
        ┌──────────────────┐
        │ LLM / Agent      │
        │ LangGraph        │
        │ Ollama / GLM API │
        └──────────────────┘
```

## 2. 后端总体分层
遵循 DDD + OOP + Clean Architecture 思想，严格分离业务逻辑与基础设施。

```text
backend/
├── app/
│   ├── api/                    # API / Controller 层
│   │   ├── dto.py              # 请求/响应模型（pydantic）
│   │   ├── errors.py           # 统一 AppError 体系与全局异常处理器
│   │   └── routes/             # conversations / chat / documents 路由
│   │
│   ├── application/            # Application 层：业务流程编排
│   │   └── services/
│   │       ├── chat_service.py          # 问答编排（会话持久化 + 工作流端口）
│   │       ├── conversation_service.py  # 会话生命周期与消息持久化
│   │       ├── document_pipeline.py     # 文档解析→清洗→切分（解析器工厂）
│   │       ├── document_service.py      # 文档元数据状态机 + 入库/删除
│   │       ├── knowledge_service.py     # Pipeline→Embedding→VectorStore 入库
│   │       └── rag_service.py           # 检索与上下文构建
│   │
│   ├── domain/                 # Domain 层：实体 + 端口（零技术依赖）
│   │   ├── entities/           # conversation / message / document / chunk / llm
│   │   ├── repositories/       # Database / Conversation / Message / Document / VectorStore / LLMProvider 端口
│   │   └── services/           # document_parser / embedding / qa_workflow 端口
│   │
│   ├── infrastructure/         # 基础设施实现（实现领域端口）
│   │   ├── database/
│   │   │   ├── sqlite/         # SQLiteDatabase（aiosqlite）
│   │   │   └── mysql/          # 预留
│   │   ├── vector_store/
│   │   │   ├── chroma.py       # ChromaVectorStore
│   │   │   └── milvus.py       # Milvus 骨架（预留）
│   │   ├── llm/
│   │   │   ├── ollama.py       # OllamaProvider
│   │   │   └── glm.py          # GLMProvider
│   │   ├── document_parser/
│   │   │   ├── pdf_parser.py   # PdfParser（pypdf）
│   │   │   └── text_parser.py  # TextParser（txt/md，多编码回退）
│   │   └── embedding/
│   │       └── ollama_embedding.py  # OllamaEmbeddingService
│   │
│   ├── agent/                  # LangGraph Agent（问答工作流，实现 QaWorkflow 端口）
│   │   ├── __init__.py         # 对外唯一入口：create_qa_workflow 工厂
│   │   ├── graph.py            # 工作流构建（retrieve?→generate，流式经 stream writer）
│   │   ├── prompts.py          # 法律问答策略 Prompt
│   │   └── state.py            # AgentState
│   │                           # ※ 全项目唯一允许导入 langgraph 的业务模块
│   │
│   ├── common/                 # 横切基础设施
│   │   ├── di.py               # 轻量 DI 容器
│   │   └── logging.py          # 结构化 JSON 日志
│   │
│   ├── config/
│   │   └── settings.py         # 统一配置（pydantic-settings，相对路径锚定 backend/）
│   │
│   ├── containers.py           # 唯一依赖装配点（工厂 + 单例注册）
│   └── main.py                 # 应用入口（lifespan / CORS / 路由 / 异常处理）
│
├── tests/
│   ├── unit/                   # 单元测试：纯逻辑与抽象层，无外部 IO
│   ├── integration/            # 集成测试：真实 SQLite/Chroma/MockTransport/完整应用
│   └── data_source/            # RAG 测试数据源（真实法律文档）
├── scripts/                    # 手工验证脚本（Ollama 流式 / 真实 embedding / E2E）
├── pyproject.toml
├── uv.lock
└── .env                        # 本地敏感配置（gitignore，模板见 .env.example）
```

### 分层依赖原则
```text
API
 ↓
Application（经领域端口使用工作流/基础设施能力）
 ↓
Domain（实体 + 端口，零技术依赖）
 ↑
Infrastructure implements Domain ports
```

### 领域端口清单（抽象定义位置）
| 端口 | 定义位置 | 当前实现 |
|------|---------|---------|
| `Database` / `TransactionContext` | domain/repositories/database.py | SQLiteDatabase |
| `ConversationRepository` / `MessageRepository` / `DocumentRepository` | domain/repositories/ | SQLiteDatabase 内置仓库 |
| `VectorStore` | domain/repositories/vector_store.py | ChromaVectorStore（Milvus 骨架预留） |
| `LLMProvider` | domain/repositories/llm_provider.py | OllamaProvider / GLMProvider |
| `DocumentParser` | domain/services/document_parser.py | TextParser / PdfParser |
| `EmbeddingService` | domain/services/embedding.py | OllamaEmbeddingService |
| `QaWorkflow` | domain/services/qa_workflow.py | LangGraph 工作流（agent/，经 `create_qa_workflow` 工厂暴露） |

### 合规守护
- 领域层禁止导入任何技术库（fastapi/httpx/chromadb/aiosqlite/pypdf/langgraph/pydantic 等）与应用层。
- 应用层与 API 层禁止导入 `app.infrastructure`，只能依赖领域端口。
- langgraph 是工作流引擎隔离区：只允许 `app/agent/` 导入；模块外部一律经 `app.agent.create_qa_workflow` 工厂获取工作流，不感知引擎存在。
- 上表所列抽象只允许定义在 domain 层；新增端口时同步更新本清单。
- 以上规则由 `backend/tests/unit/test_ddd_boundaries.py` 在每次 pytest 时以 AST 扫描机械校验（曾据此发现并修复 Database 端口错位、chat_service 依赖 langgraph 类型等违例）。
- Domain 不依赖 FastAPI、SQLite、Chroma、Ollama 等具体技术。
- Application 负责业务流程编排。
- Infrastructure 负责数据库、向量库、LLM、文件解析等具体实现。
- API 只负责 HTTP 参数、认证、响应及流式输出。
- 禁止在 API 层直接访问数据库。
- 禁止 Domain 层直接依赖具体数据库实现。

##

## 3. Agent 架构
使用 LangGraph 实现 Agent 工作流。
```text
User Question
      │
      ▼
Load Conversation Context
      │
      ▼
Query Understanding
      │
      ▼
Knowledge Retrieval
      │
      ▼
Context Construction
      │
      ▼
LLM Reasoning
      │
      ▼
Answer
      │
      ├──────────────► Stream to Frontend
      │
      ▼
Persist Message
```

## 4. 知识库数据流
用户上传 PDF / TXT / MD：

```text
Frontend
   │
   │ multipart/form-data
   ▼
Document API
   │
   ▼
KnowledgeService
   │
   ▼
DocumentParserFactory
   │
   ├── PDFParser
   └── TextParser
   │
   ▼
Text
   │
   ▼
Text Chunking
   │
   ▼
EmbeddingService
   │
   ▼
VectorStore
   │
   ├── Chroma
   └── Milvus
   │
   ▼
DocumentRepository
```

## 9. 用户问答数据流

```text
Frontend
   │
   │ POST /api/chat/stream
   ▼
ChatController
   │
   ▼
ChatService
   │
   ├── Load Conversation
   ├── Save User Message
   │
   ▼
LangGraph Agent
   │
   ▼
SSE Stream
   │
   ▼
Frontend incremental rendering
   │
   ▼
Save Assistant Message
```

## 10. 流式响应
后端使用 FastAPI StreamingResponse / SSE。

```text
LLM
 ↓
Agent
 ↓
ChatService
 ↓
Async Generator
 ↓
FastAPI StreamingResponse
 ↓
SSE
 ↓
Fetch ReadableStream
 ↓
React State
 ↓
实时渲染 Markdown
```

要求：

- 全链路异步。
- 不允许阻塞事件循环。
- LLM Token 按流实时返回。
- Assistant 最终完整内容必须持久化。
- 流式过程中发生异常时返回统一错误事件。

---

## 12. 前端架构

整体交互参考 Codex Web UI。

## 13. 标准启动与验证路径

### 后端启动路径（BE-001 起生效）
```bash
cd backend
uv sync                 # 创建/同步 .venv 虚拟环境（Python 3.11.15）
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 后端验证路径
```bash
curl http://127.0.0.1:8000/api/health   # 期望 {"status": "ok"}
```
- 服务启动时输出结构化 JSON 日志（见 docs/RELIABILITY.md）。
- OpenAPI 文档位于 http://127.0.0.1:8000/docs 。

## 14. 配置管理（BE-002）

### 统一配置入口
所有运行参数通过 `backend/app/config/settings.py` 的 `Settings`（pydantic-settings）读取，业务代码通过 `get_settings()` 获取单例，禁止在业务代码中直接读取环境变量。

### Provider 切换
通过配置（环境变量或 `.env`）切换 Provider，业务代码零修改：

| 配置项 | 取值 | 默认 |
|-------|------|------|
| `DB_PROVIDER` | sqlite / mysql | sqlite |
| `VECTOR_STORE_PROVIDER` | chroma / milvus | chroma |
| `LLM_PROVIDER` | ollama / glm | ollama |

其余运行参数：服务地址端口（`HOST`/`PORT`）、日志等级（`LOG_LEVEL`）、SQLite 文件路径（`SQLITE_DB_PATH`）、MySQL 连接串（`MYSQL_URL`）、Chroma 持久化目录（`CHROMA_PERSIST_DIR`）、Milvus 地址（`MILVUS_URI`）、Ollama 地址与模型（`OLLAMA_BASE_URL`/`OLLAMA_MODEL`）、GLM 地址与模型（`GLM_BASE_URL`/`GLM_MODEL`）。

### 敏感配置
`GLM_API_KEY` 等密钥只通过环境变量或本地 `.env`（已被 .gitignore 排除）注入，禁止硬编码、禁止提交仓库；日志中禁止输出密钥明文。

## 15. 依赖注入与工厂（BE-003）

### 机制
- `backend/app/common/di.py` 提供轻量 `DIContainer`：按抽象接口注册工厂（工厂模式），支持单例缓存（单例模式）。
- `backend/app/containers.py` 的 `create_container()` 是全应用唯一装配点：读取 `Settings`，按配置把具体实现注册到抽象接口上。

### 依赖方向（依赖倒置）
```text
API / Application Service ──依赖──▶ 抽象接口（domain/repositories 等）
                                        ▲
具体实现（SQLite/Chroma/Ollama/GLM）────┘ 由容器在装配点注入
```
- 业务代码只 import 抽象接口，禁止 import 具体实现模块。
- 切换 Provider = 修改配置 + 容器注册对应工厂，业务代码零修改。
- 测试可向容器注册 Fake 实现替代真实基础设施。

## 16. 数据库抽象层（BE-004）

### 领域实体（数据契约）
纯 Python dataclass，位于 `backend/app/domain/entities/`，不依赖任何数据库技术：
- `Conversation`：id、title、created_at
- `Message`：id、conversation_id、role（user/assistant/system）、content、created_at
- `Document`：id、filename、file_size、status（pending/processing/ready/failed）、created_at

### Repository 接口
位于 `backend/app/domain/repositories/`，全部为抽象基类：
- `ConversationRepository`：create / get / list / delete
- `MessageRepository`：add / list_by_conversation / delete_by_conversation
- `DocumentRepository`：create / get / list / delete / update_status

### Database 抽象
位于 `backend/app/domain/repositories/database.py`（领域端口，依赖倒置）：
- `connect()` / `init_schema()` / `close()` 生命周期方法
- `transaction()` 异步上下文管理器：事务内的仓库操作要么全部提交要么全部回滚
- `conversations` / `messages` / `documents` 三个仓库实例由具体实现提供

SQLite 实现（BE-005）与未来 MySQL 实现均实现此抽象，业务层通过依赖注入获取 `Database` 实例。

## 17. SQLite 实现（BE-005）

- 依赖 `aiosqlite`，连接对象由 `SQLiteDatabase` 持有，业务层不可见。
- 数据库文件路径来自配置 `SQLITE_DB_PATH`（默认 `data/law_agent.db`）。
- 相对路径统一锚定到 `backend/` 目录（`Settings.resolved_sqlite_db_path` / `resolved_chroma_persist_dir`），数据位置不随进程工作目录变化——避免在不同目录启动服务时数据被写到错误位置。
- 应用启动时（FastAPI lifespan）执行 `connect()` + `init_schema()`，关闭时 `close()`；建表使用 `IF NOT EXISTS`，保证幂等。
- 表结构：`conversations`、`messages`（外键 conversation_id，级联删除，需开启 `PRAGMA foreign_keys`）、`documents`。
- 容器装配点按 `DB_PROVIDER` 注册：sqlite → `SQLiteDatabase`；mysql → 明确的"未实现"错误（预留）。

## 18. 向量数据库抽象层（BE-006）

### 数据契约
- `DocumentChunk`（domain/entities）：chunk_id、document_id、content、chunk_index、metadata（文件名等来源信息）
- `RetrievedChunk`：chunk + score（相似度得分，越高越相关）

### VectorStore 抽象接口（domain/repositories/vector_store.py）
- `add_chunks(chunks, embeddings) -> list[str]`：写入 chunk 及其向量，返回生成的 chunk id
- `search(query_embedding, top_k) -> list[RetrievedChunk]`：按向量相似度检索
- `delete_by_document(document_id) -> int`：删除某文档的全部 chunk，返回删除数量
- `initialize()` / `close()`：生命周期方法

### 实现与选择
- Chroma 实现（BE-007）：`infrastructure/vector_store/chroma.py`
- Milvus 预留（BE-008）：`infrastructure/vector_store/milvus.py`
- Embedding 由调用方（BE-013 EmbeddingService）生成后传入，向量库抽象不关心 embedding 模型；
  这保证向量库实现与 embedding 模型彻底解耦。
- 容器装配点按 `VECTOR_STORE_PROVIDER` 注册实现。

## 19. Chroma 实现（BE-007）

- 依赖 `chromadb`，使用 `PersistentClient` 持久化到配置 `CHROMA_PERSIST_DIR`（默认 `data/chroma`）。
- 集合名 `law_chunks`，向量空间使用 cosine（保证 score = 1 - distance ∈ [0,1]，越大越相关）。
- chunk 原文作为 document 存储，metadata 保存 `document_id`、`chunk_index` 与来源信息；`delete_by_document` 通过 metadata 过滤实现。
- 接口中的 embedding 均由调用方显式传入，不使用 Chroma 内置 embedding 函数（与 embedding 模型解耦，且避免启动时下载模型）。

## 20. Milvus 扩展架构（BE-008）

- `infrastructure/vector_store/milvus.py` 提供 `MilvusVectorStore` 骨架：履行 VectorStore 接口签名，任何实际调用抛出明确的 `NotImplementedError`（第一版不做完整实现）。
- 容器装配点按 `VECTOR_STORE_PROVIDER` 分支：chroma → `ChromaVectorStore`；milvus → `MilvusVectorStore` 骨架。切换 Provider 只改配置。
- 核心约束：RAG/Agent 业务代码只 import `domain/repositories/vector_store.py` 抽象，不存在 Chroma 强耦合；Milvus 完整实现落地时只新增/替换基础设施文件，业务层零修改。

## 21. LLM Provider 抽象层（BE-009）

### 数据契约
- `ChatMessage`（domain/entities/llm.py）：role（复用 MessageRole：user/assistant/system）+ content

### LLMProvider 抽象接口（domain/repositories/llm_provider.py）
- `chat(messages, temperature, max_tokens) -> str`：同步问答，返回完整回答
- `stream(messages, temperature, max_tokens) -> AsyncIterator[str]`：流式问答，按 token 增量产出
- 两个方法都必须可被 LangGraph Agent 与上层 Service 直接消费，且不暴露任何具体厂商协议

### 实现与选择
- Ollama（BE-010）：`infrastructure/llm/ollama.py`
- GLM（BE-010）：`infrastructure/llm/glm.py`
- 容器装配点按 `LLM_PROVIDER` 注册实现；LangGraph Agent 只依赖抽象接口。

## 22. Ollama 与 GLM 实现（BE-010）

### OllamaProvider（infrastructure/llm/ollama.py）
- `POST {OLLAMA_BASE_URL}/api/chat`：`stream:false` 一次性返回；`stream:true` 返回 NDJSON，逐行解析 `message.content`。
- 模型来自 `OLLAMA_MODEL`，服务地址来自 `OLLAMA_BASE_URL`。

### GLMProvider（infrastructure/llm/glm.py）
- `POST {GLM_BASE_URL}/chat/completions`（OpenAI 兼容协议），`Authorization: Bearer {GLM_API_KEY}`。
- `stream:false` 取 `choices[0].message.content`；`stream:true` 解析 SSE `data:` 行中的 `choices[0].delta.content`。

### 通用要求
- 网络调用基于 httpx.AsyncClient，全链路异步；敏感的 `GLM_API_KEY` 只从环境变量注入，日志中禁止输出。
- 模型产出前先输出结构化日志（服务、模型名、消息数），失败时输出 ERROR 日志并抛出可识别异常。

## 23. 文档处理 Pipeline（BE-011）

### 流程
```text
文件接收(filename, bytes)
   → 格式识别(扩展名, 工厂选择解析器)
   → 文本解析(DocumentParser 策略)
   → 文本清洗(去控制字符、归一化换行与空行)
   → Chunk 切分(段落感知：法条段落优先完整，单段超限退化为定长+重叠窗口)
   → 构建 DocumentChunk(content, chunk_index, metadata={filename,...})
```

### 结构
- 解析器接口 `DocumentParser`（domain/services/document_parser.py）：`supports(filename)` + `parse(content) -> str`，策略模式；新格式（如 PDF）注册进工厂即可，Pipeline 不感知格式细节。
- `DocumentParserFactory`（application/services/document_pipeline.py）：按文件名选择解析器，无匹配时抛 `UnsupportedFormatError`。
- `DocumentPipeline`（application/services/document_pipeline.py）：编排上述全流程并输出结构化日志（开始：文件名与大小；完成：chunk 数量）。
- 切分策略（段落感知）：`chunk_size`（默认 500 字符）、`chunk_overlap`（默认 50 字符）。优先按换行段落打包，保证一条法规完整进入同一个 chunk；仅当单段超过 chunk_size 时才退化为定长滑动窗口。背景：真实专利法测试中定长切分曾把第四十二条截断到两个 chunk，导致检索命中也答不全。

## 24. PDF 与 TXT 文档解析（BE-012）

- `infrastructure/document_parser/pdf_parser.py`：`PdfParser` 基于 `pypdf` 逐页提取文本后拼接；解析结果为空（扫描件/纯图片 PDF）时抛出明确异常，由上层记录失败状态。
- `infrastructure/document_parser/text_parser.py`：`TextParser` 处理 TXT/MD，UTF-8 失败后回退 gb18030/big5。
- 两个解析器均实现 `DocumentParser` 策略接口，由 `DocumentParserFactory` 按扩展名分发（.pdf / .txt|.md）。
- 解析失败（损坏文件、空文档、未知编码）都抛出带原因的异常，Pipeline 上层据此将 Document 标记为 failed 并记录 ERROR 日志。

## 25. Embedding 与知识库入库（BE-013）

### Embedding 抽象
- `EmbeddingService`（domain/services/embedding.py）：`embed_documents(texts) -> list[vector]`（批量，入库用）与 `embed_query(text) -> vector`（单条，检索用）。
- `OllamaEmbeddingService`（infrastructure/embedding/ollama_embedding.py）：调用 `POST {OLLAMA_BASE_URL}/api/embed` 批量生成向量；模型来自 `OLLAMA_EMBEDDING_MODEL` 配置。

### 知识库入库服务
- `KnowledgeIngestionService`（application/services/knowledge_service.py）：编排 `DocumentPipeline`（解析/清洗/切分）→ 回填 document_id → `EmbeddingService` 批量向量化 → `VectorStore.add_chunks` 写入。
- 全流程结构化日志：开始（文件名/大小）、向量化（chunk 数）、完成（chunk id 数）。
- 依赖全部来自抽象接口（Pipeline 组合、EmbeddingService、VectorStore），可整体替换任一实现。

## 26. RAG 检索服务（BE-014）

- `RagService`（application/services/rag_service.py）：`retrieve(query, top_k)` 编排 `EmbeddingService.embed_query` → `VectorStore.search`，返回带来源信息的 `RetrievedChunk` 列表。
- 另提供 `build_context(results)`：把检索结果格式化为供 LLM 使用的上下文文本（含来源文件名），空结果返回空串。
- 依赖仅抽象接口（EmbeddingService、VectorStore），检索过程输出结构化日志（query 长度、命中数、最高分）。

## 27. LangGraph Agent 工作流（BE-015/BE-016）

### 状态
- `AgentState`（agent/state.py）：question（用户问题）、history（历史消息）、context（检索上下文）、answer（模型回答）。

### 基础工作流（BE-015）
```text
START → generate（组装消息调用 LLMProvider）→ END
```

### RAG 工作流（BE-016）
```text
START → retrieve（RagService.build_context 写入 state.context）
      → generate（上下文 + 问题组装 Prompt 调用 LLM）→ END
```

- `build_qa_graph(llm, rag=None)`（agent/graph.py）：rag 为 None 时为基础工作流，传入即为 RAG 工作流；节点全异步，LLM 调用只经过 LLMProvider 抽象。
- Prompt 组装集中在 `agent/prompts.py`，回答策略（BE-017）只改该文件。

### 统一执行路径（所有 LLM 问答必须走图）
- generate 节点内通过 `LLMProvider.stream` 生成，并经 `get_stream_writer()` 推送 token。
- 非流式：`graph.ainvoke(...)`（writer 事件无人消费，行为不变）；流式：`graph.astream(..., stream_mode="custom")` 逐 token 产出。
- 禁止在图外直连 LLMProvider 做问答——保证检索、Prompt、模型调用只有一份实现。
- ChatService 是图的唯一消费方：只依赖 `QaWorkflow` 领域端口（domain/services/qa_workflow.py），LangGraph 是可整体替换的实现细节；ChatService 负责会话历史快照与问答持久化，不直接依赖 RAG/LLM。

## 28. 对话服务（BE-018）

- `ConversationService`（application/services/conversation_service.py）：会话生命周期与消息持久化的唯一业务入口。
  - `create_conversation(title)`：空标题默认"新对话"
  - `list_conversations()` / `get_messages(conversation_id)` / `delete_conversation(conversation_id)`
  - `add_user_message` / `add_assistant_message`：供 Chat 流程持久化问答
- 会话不存在时抛 `ConversationNotFoundError`；删除会话时同时清理其全部消息。
- 依赖仅 Database 抽象；标题与消息数变更输出结构化日志。

## 29. FastAPI 核心 API（BE-019/020/021）

所有 API 均为异步函数，业务逻辑只调用 Service 层；统一错误结构 `{"code": <int>, "message": <str>}`，业务异常（会话不存在等）由全局异常处理器映射为对应状态码。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/conversations | 创建对话（title 可选） |
| GET | /api/conversations | 对话列表 |
| GET | /api/conversations/{id}/messages | 会话消息 |
| DELETE | /api/conversations/{id} | 删除会话（级联消息） |
| POST | /api/chat/stream | 提交问题，SSE 流式返回回答（BE-020） |
| POST | /api/documents | 上传 PDF/TXT（multipart，BE-021） |
| GET | /api/documents | 文档列表 |
| DELETE | /api/documents/{id} | 删除文档（级联向量） |

### Chat 流式协议（SSE，data: {json}\n\n）
```json
{"type": "delta", "content": "增量文本"}
{"type": "done", "conversation_id": "...", "message_id": "..."}
{"type": "error", "message": "..."}
```
流结束前 Assistant 完整回答必须持久化；流中异常以 error 事件返回而非中断连接。

### Document Upload（BE-021）
- 校验：扩展名白名单（不支持→400）、大小上限 20MB（超限→413）。
- 流程：DocumentService 创建元数据(processing) → KnowledgeIngestionService 入库 → 状态 ready/failed；DELETE 时同时删除向量与元数据。

