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
│   │
│   ├── application/            # Application 层
│   │   ├── services/
│   │   └── dto/
│   │
│   ├── domain/                 # Domain 层，核心业务
│   │   ├── entities/
│   │   ├── repositories/
│   │   └── services/
│   │
│   ├── infrastructure/         # 基础设施实现
│   │   ├── database/
│   │   │   ├── sqlite/
│   │   │   └── mysql/
│   │   ├── vector_store/
│   │   │   ├── chroma.py
│   │   │   └── milvus.py
│   │   ├── llm/
│   │   │   ├── ollama.py
│   │   │   └── glm.py
│   │   ├── document_parser/
│   │   │   ├── pdf_parser.py
│   │   │   └── text_parser.py
│   │   └── embedding/
│   │
│   ├── agent/                  # LangGraph Agent
│   │   ├── graph.py
│   │   ├── state.py
│   │   ├── nodes/
│   │   └── tools/
│   │
│   ├── config/                 # 配置
│   │   └── settings.py
│   │
│   └── main.py
│
├── tests/
├── pyproject.toml
├── uv.lock
└── .env
└── xxx
```

### 分层依赖原则
```text
API
 ↓
Application
 ↓
Domain
 ↑
Infrastructure implements Domain interfaces
```
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
用户上传 PDF / TXT：

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
VectorStore.search()
   │
   ▼
Retrieved Knowledge
   │
   ▼
LLMProvider.stream()
   │
   ├── Ollama
   └── GLM
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
位于 `backend/app/infrastructure/database/base.py`：
- `connect()` / `init_schema()` / `close()` 生命周期方法
- `transaction()` 异步上下文管理器：事务内的仓库操作要么全部提交要么全部回滚
- `conversations` / `messages` / `documents` 三个仓库实例由具体实现提供

SQLite 实现（BE-005）与未来 MySQL 实现均实现此抽象，业务层通过依赖注入获取 `Database` 实例。

