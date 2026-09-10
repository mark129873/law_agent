# Architecture

## 0. 简单描述
-后端使用python3.11.15, 使用uv进行环境管理,.venv是虚拟环境
-后端使用fastapi, 接口使用异步函数
-后端使用langraph, 大模型支持ollama本地部署以及使用glm的api, 
-数据库此版本支持sqlite3, 后续版本支持mysql8.0根据配置进行切换, 做好数据库接口层抽象
-数据库实现统一走 SQLAlchemy 2.0 async Core（方言无关的表结构与 DML），SQLite 是当前唯一已启用的 Provider，MySQL 8.0 接入只需换 URL 与异步驱动
-向量数据库支持chroma, 后续版本支持milvus根据配置进行切换, 做好向量数据库接口层抽象

## 1. 系统概览

法律知识库与法律问答 Agent，前后端分离：

```text
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                            │
│        React + TypeScript + Vite + Tailwind CSS            │
│              Chat / 会话管理 / 知识库管理（待开发）           │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP / SSE
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                Backend（DDD 分层 + 依赖注入）                 │
│  API 层 ──▶ Application 层 ──▶ Domain 层（实体 + 端口）      │
│                    ▲                     ▲                  │
│                    └── Infrastructure 层实现领域端口          │
│  Agent 模块（LangGraph，实现 QaWorkflow 端口）                │
└──────────────┬──────────────────┬───────────────────────────┘
               ▼                  ▼
      ┌────────────────┐  ┌────────────────┐
      │ SQLite → MySQL │  │ Chroma → Milvus│
      └────────────────┘  └────────────────┘
               │
               ▼
      ┌─────────────────────────────┐
      │ LLM：Ollama 本地 / GLM API  │
      └─────────────────────────────┘
```

技术栈：Python 3.11 + FastAPI（全异步）+ uv 环境管理 + LangGraph + SQLAlchemy 2.0 async Core（当前挂 aiosqlite 驱动）+ Chroma + httpx。
前端技术栈：React 19 + TypeScript（严格模式）+ Vite 8 + Tailwind CSS v4 + React Router 7 + 原生 Fetch（无 axios）。

## 2. 目录结构

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
│   │       ├── chat_service.py          # 问答编排（会话持久化 + QaWorkflow 端口）
│   │       ├── conversation_service.py  # 会话生命周期与消息持久化
│   │       ├── document_pipeline.py     # 解析→清洗→段落感知切分（解析器工厂）
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
│   │   ├── database/sqlalchemy/ # SQLAlchemyDatabase（schema.py 表结构 / types.py 时区无损时间列 / database.py 端口实现）；方言无关，MySQL 预留靠 URL 切换
│   │   ├── vector_store/       # ChromaVectorStore；milvus.py 骨架预留
│   │   ├── llm/                # OllamaProvider / GLMProvider
│   │   ├── document_parser/    # PdfParser（pypdf）/ TextParser（txt/md，多编码回退）
│   │   └── embedding/          # OllamaEmbeddingService（/api/embed 批量）
│   │
│   ├── agent/                  # LangGraph Agent（※ 全项目唯一允许导入 langgraph 的业务模块）
│   │   ├── __init__.py         # 对外唯一入口：create_qa_workflow 工厂
│   │   ├── graph.py            # QaGraphBuilder 建造者 + LangGraphQaWorkflow 适配器
│   │   ├── nodes.py            # AgentNode 抽象基类 + Retrieve/Generate 节点（命令模式）
│   │   ├── prompts.py          # 法律问答策略 Prompt
│   │   └── state.py            # AgentState
│   │
│   ├── common/                 # 横切基础设施：di.py 轻量容器 / logging.py 结构化 JSON 日志
│   ├── config/settings.py      # 统一配置（pydantic-settings，相对路径锚定 backend/）
│   ├── containers.py           # 唯一依赖装配点（工厂 + 单例注册）
│   └── main.py                 # 应用入口（lifespan / CORS / 路由 / 异常处理）
│
├── tests/
│   ├── unit/                   # 单元测试：纯逻辑与抽象层，无外部 IO
│   ├── integration/            # 集成测试：真实 SQLite/Chroma/MockTransport/完整应用
│   └── data_source/            # RAG 测试数据源（真实法律文档）
├── scripts/                    # 手工验证脚本（Ollama 流式 / 真实 embedding / E2E）
├── pyproject.toml / uv.lock
└── .env                        # 本地敏感配置（gitignore，模板见 .env.example）
```

```text
frontend/                        # 前端独立项目（React + TS + Vite）
├── index.html                   # 唯一 HTML 入口（React 挂载点 #root）
├── vite.config.ts               # React/Tailwind v4 插件；dev 期 /api 代理到 127.0.0.1:8000
├── tsconfig.json                # TS 严格模式；build 前先 tsc --noEmit 类型检查
├── package.json                 # npm 依赖与脚本（dev / build / preview）
└── src/
    ├── main.tsx                 # 应用入口：BrowserRouter（路由）> AppProvider（状态）> App
    ├── App.tsx                  # 路由表（URL → 页面组件），集中一处便于总览
    ├── index.css                # Tailwind v4 入口 + 语义化主题 token（明暗双主题跟随系统）
    ├── vite-env.d.ts            # Vite 内置 API 与样式导入的类型声明
    ├── types/index.ts           # 与后端契约一一对应的类型（会话/消息/文档/错误/SSE 事件）
    ├── api/                     # 统一数据访问层（FE-002）：UI 组件禁止直接 fetch
    │   ├── client.ts            # request<T> 封装 + ApiError（解析统一错误结构 {code,message}）
    │   ├── health.ts            # 健康检查（连接状态指示）
    │   ├── conversations.ts     # 会话列表/创建/消息/删除
    │   ├── documents.ts         # 文档列表/上传(multipart)/删除 + 白名单与大小上限常量
    │   └── chat.ts              # 流式问答：fetch 消费 SSE，拆分 delta/done/error 事件
    ├── state/AppContext.tsx     # 轻量全局状态（React Context）：会话/消息/文档/视图与业务动作
    ├── pages/                   # 页面组件（对话页 / 知识库页）
    ├── components/              # 通用组件（侧边栏、消息块、上传面板等）
    └── utils/format.ts          # 纯函数工具（文件大小/日期格式化）
```

### 前端数据流（FE-002 起）
- UI 组件一律经 `state/AppContext` 的动作方法读写数据，动作内部调用 `api/*` 模块，组件禁止直接 `fetch`，请求与错误解析只保留一份实现。
- 错误契约：后端非 2xx 统一 `{code,message}`，`api/client.ts` 解析为 `ApiError` 抛出，UI 展示 `message`。
- 提问数据流（FE-004）：ChatPage 输入框 → `AppContext.sendQuestion` →（无会话时先 `POST /api/conversations`，title=提问截短 20 字）→ 本地乐观插入 user 消息与空 assistant 消息 → `api/chat.ts` 消费 SSE，delta 增量写回 messages → done 后由后端持久化；error 移除空占位并展示错误条。
- 回答渲染（FE-010）：助手消息经 `react-markdown` 渲染（模型输出含 Markdown 格式；默认不解析原始 HTML，无 XSS 风险）；用户消息保持纯文本。流式过程中的未闭合标记会短暂显示为字面字符，完成后即正常渲染。
- 参考文档（FE-011）：`api/chat.ts` 消费 `sources` 事件暂存来源，done 后随助手消息写入本地状态；消息带 `sources`（含历史恢复的消息）且不在流式生成中时渲染「参考文档」折叠按钮，点开按序号显示文档名与命中内容；来源内容按纯文本渲染（不进 Markdown 解析）。
- 图标统一使用 `@phosphor-icons/react`；不手绘 SVG 图标，不引入第二套图标族。

## 3. 分层架构与领域端口

### 分层依赖原则
```text
API ──▶ Application ──▶ Domain（实体 + 端口，零技术依赖）
                            ▲
Infrastructure implements Domain ports
Agent（工作流实现，独立模块）──▶ Domain 端口 + Application 服务
```
- 业务代码只依赖领域端口；具体实现由 `containers.py`（唯一装配点）按配置注入。
- `common/di.py` 提供轻量 `DIContainer`：按抽象接口注册工厂（工厂模式），单例缓存（双重检查锁，支持依赖链装配）。
- 配置读取统一走 `config/settings.py` 的 `get_settings()`，禁止业务代码散读环境变量。

### 领域端口清单
| 端口 | 定义位置 | 当前实现 |
|------|---------|---------|
| `Database` / `TransactionContext` | domain/repositories/database.py | SQLAlchemyDatabase（infrastructure/database/sqlalchemy/） |
| `ConversationRepository` / `MessageRepository` / `DocumentRepository` | domain/repositories/ | SQLAlchemyDatabase 内置仓库（Core 表达式，方言无关） |
| `VectorStore` | domain/repositories/vector_store.py | ChromaVectorStore（Milvus 骨架预留） |
| `LLMProvider` | domain/repositories/llm_provider.py | OllamaProvider / GLMProvider |
| `DocumentParser` | domain/services/document_parser.py | TextParser / PdfParser |
| `EmbeddingService` | domain/services/embedding.py | OllamaEmbeddingService |
| `QaWorkflow` | domain/services/qa_workflow.py | LangGraph 工作流（agent/，经 `create_qa_workflow` 工厂暴露） |

### 排序职责（BE-024）
- **仓储只负责读写，不负责排序**：三个 Repository 的 `list` / `list_by_conversation` 不再输出 SQL `ORDER BY`（原 `ORDER BY created_at ASC, rowid ASC` 依赖 SQLite 专有的 `rowid`，MySQL 无此概念）。
- **排序规则集中在应用服务层，且只按创建时间判断**：`ConversationService.list_conversations`（`created_at` 正序）、`ConversationService.get_messages`（`created_at` 正序）、`DocumentService.list_documents`（`created_at` 倒序）。交换任何数据库实现，排序行为不变。
- 同一 `created_at`（微秒级相同）的记录没有第二排序键：输出顺序由底层返回顺序决定，Python `sorted` 的稳定性保证同一份数据重复查询结果一致；不再引入"物理行号"这类存储耦合的兜底键。

### 合规守护
- 领域层禁止导入任何技术库（fastapi/httpx/chromadb/sqlalchemy/aiosqlite/pypdf/langgraph/pydantic 等）与应用层。
- 应用层与 API 层禁止导入 `app.infrastructure`，只能依赖领域端口。
- langgraph 是工作流引擎隔离区：只允许 `app/agent/` 导入；模块外部一律经 `app.agent.create_qa_workflow` 工厂获取工作流，不感知引擎存在。
- sqlalchemy 是数据库技术隔离区：只允许 `app/infrastructure/database/` 导入；业务层拿到的永远是领域实体与端口。
- 上表所列抽象只允许定义在 domain 层；新增端口时同步更新本清单。
- 以上规则由 `backend/tests/unit/test_ddd_boundaries.py` 在每次 pytest 时以 AST 扫描机械校验（曾据此发现并修复 Database 端口错位、chat_service 依赖 langgraph 类型等违例）。

## 4. 核心数据流

### RAG 问答全链路（流式）
```text
POST /api/chat/stream {conversation_id, question}
  ▼ ChatService：历史快照 → 保存用户消息 → astream(stream_mode="custom")
  ▼ LangGraph 图：retrieve（RagService 检索 + build_context）→ generate（build_messages → LLMProvider.stream）
  ▼ retrieve 命中时经 get_stream_writer 推送 sources 事件（参考来源，先于一切 delta）
  ▼ generate 节点逐 token 推送 delta 事件（领域事件 QaStreamEvent 统一承载）
  ▼ SSE：data: {"type":"sources","sources":[...]}（仅检索有命中时出现）
       data: {"type":"delta","content":"增量"} ... {"type":"done"} / {"type":"error"}
  ▼ 流正常结束：完整回答与参考来源一起持久化为 assistant 消息（异常中断不落库）
```
- **所有 LLM 问答必须走图**：流式与非流式执行同一节点，检索、Prompt 组装、模型调用只有一份实现；禁止在图外直连 LLMProvider 做问答。
- ChatService 只依赖 `QaWorkflow` 端口，负责会话持久化，不直接依赖 RAG/LLM。

### 文档入库全链路
```text
POST /api/documents (multipart)
  ▼ DocumentService：扩展名白名单（不支持→400）→ 大小上限 20MB（超限→413）
  ▼ 创建元数据(processing) → DocumentPipeline：格式识别→解析→清洗→段落感知切分→chunk
  ▼ 回填 document_id → EmbeddingService 批量向量化 → VectorStore.add_chunks
  ▼ 状态机：processing → ready（chunk 为空或异常 → failed，不产生僵尸记录）
DELETE /api/documents/{id}：向量按 document_id 删除 + 元数据删除（必须同时清理）
```
- 切分策略（段落感知）：`chunk_size` 默认 500 字符、`chunk_overlap` 默认 50。优先按换行段落打包保证一条法规完整入同一个 chunk，单段超限才退化为定长滑动窗口——定长切分曾把《专利法》第四十二条截断到两个 chunk，导致检索命中也答不全。
- RAG 检索（RagService）：`embed_query → VectorStore.search`，支持 `min_score` 相似度阈值过滤弱命中；`build_context` 产出带【来源：文件名】标注的上下文，无命中返回空串，衔接"信息不足"策略。

## 5. Agent 工作流（LangGraph）

### 面向对象结构
- `AgentNode`（抽象基类）+ `RetrieveNode` / `GenerateNode`（命令模式）：`__call__` 使节点实例可直接注册进图，新增节点继承基类即可（多态）。
- `QaGraphBuilder`（建造者模式）：按是否有 RAG 装配不同拓扑，装配规则集中一处。
- `LangGraphQaWorkflow`（适配器模式）：显式继承并实现 `QaWorkflow` 领域端口，langgraph 引擎封在适配器之内。
- `create_qa_workflow(llm, rag=None)`：模块对外唯一入口（工厂），rag 为 None 时为基础工作流。

### 拓扑
```text
基础：START → generate → END
RAG： START → retrieve → generate → END
```

### 法律问答策略（agent/prompts.py，BE-017）
1. 优先依据知识库上下文回答，并注明来源文件；
2. 依据为空或不足时，明确告知"知识库中暂无相关依据，建议咨询专业律师"，禁止编造；
3. 严禁虚构法律条文、案例编号或结论；先给结论再给依据。

真实模型验证（qwen3.5:4b / glm-4.5-air）：有依据时正确引用条文与来源；无依据或检索到无关内容时明确声明信息不足，不虚构。

## 6. 配置管理

所有配置经 `config/settings.py`（pydantic-settings）读取环境变量或 `backend/.env`（模板 `.env.example`）；业务代码经 `get_settings()` 获取，禁止散读环境变量。

| 配置项 | 取值 | 默认 |
|-------|------|------|
| `DB_PROVIDER` | sqlite / mysql | sqlite |
| `VECTOR_STORE_PROVIDER` | chroma / milvus | chroma |
| `LLM_PROVIDER` | ollama / glm | ollama |
| `LLM_ENABLE_THINKING` | true / false | false（关闭思考模式） |
| `HOST` / `PORT` / `LOG_LEVEL` | — | 0.0.0.0 / 8000 / ERROR |

其余参数：`SQLITE_DB_PATH`、`MYSQL_URL`、`CHROMA_PERSIST_DIR`、`MILVUS_URI`、`OLLAMA_BASE_URL`、`OLLAMA_MODEL`（qwen3.5:4b）、`OLLAMA_EMBEDDING_MODEL`（nomic-embed-text:latest）、`GLM_BASE_URL`、`GLM_MODEL`、`GLM_API_KEY`。

- **思考模式开关（`LLM_ENABLE_THINKING`，默认 false）**：qwen3.5 / glm-4.5 等推理模型默认会先"思考"再回答，显著拉长首字延迟（真实环境曾达 30~40s）。关闭时 Ollama 请求携带 `think: false`、GLM 请求携带 `thinking: {"type": "disabled"}`；需要深度推理时可显式开启。

- **敏感配置**：`GLM_API_KEY` 等密钥只经环境变量或本地 `.env` 注入，禁止提交仓库、禁止写入日志。
- **路径锚定**：相对路径统一锚定到 `backend/`（`resolved_sqlite_db_path` / `resolved_chroma_persist_dir`），数据位置不随进程工作目录变化。
- **切换 Provider**：仅改配置，业务代码零修改；glm 缺密钥时装配即报错（尽早失败）。

## 7. API 契约

所有端点异步；统一错误结构 `{"code": <int>, "message": <str>}`（40001 格式不支持 / 40002 参数非法 / 40401 会话不存在 / 40402 文档不存在 / 41301 超限 / 50000 兜底）。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/conversations | 创建对话（title 可选，默认"新对话"） |
| GET | /api/conversations | 对话列表（创建时间正序，最早创建在上） |
| GET | /api/conversations/{id}/messages | 会话消息 |
| DELETE | /api/conversations/{id} | 删除会话（级联消息） |
| POST | /api/chat/stream | 提交问题，SSE 流式回答 |
| POST | /api/documents | 上传 PDF/TXT/MD（multipart） |
| GET | /api/documents | 文档列表 |
| DELETE | /api/documents/{id} | 删除文档（级联向量） |
| GET | /api/health | 健康检查 |

Chat 流式协议（SSE，`data: {json}\n\n`）：
```json
{"type": "sources", "sources": [{"source": "文件名", "content": "命中内容"}]}
{"type": "delta", "content": "增量文本"}
{"type": "done", "conversation_id": "..."}
{"type": "error", "message": "..."}
```
- `sources` 事件最多出现一次且先于全部 delta：仅当 RAG 检索有命中时由 retrieve 节点发出（数组顺序即展示序号）；基础工作流或检索无命中时不出现，前端据此决定是否渲染「参考文档」按钮。
- 参考来源随回答持久化（messages 表 `sources` JSON 列，旧库启动时自动 ALTER 迁移），`GET /api/conversations/{id}/messages` 原样返回，历史消息同样可展示参考文档。
CORS 当前 `allow_origins=["*"]`（开发态，生产需收敛）。OpenAPI 文档：`http://127.0.0.1:8000/docs`。

## 8. 启动与验证

```bash
cd backend
uv sync                                            # 创建/同步 .venv（Python 3.11）
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```
```bash
uv run pytest                                      # 全量测试（含 DDD 边界守护）
curl http://127.0.0.1:8000/api/health              # {"status":"ok"}
```
```bash
cd frontend                                        # 前端（FE-001）
npm install                                        # 安装依赖（Node 20+）
npm run dev                                        # 开发服务器 http://localhost:5173（/api 代理到 8000）
npm run build                                      # tsc 类型检查 + 生产构建（dist/）
```
- 启动时 lifespan 自动：SQLite connect + init_schema（幂等建表）、Chroma initialize；关闭时释放。
- 日志：单行 JSON（timestamp/level/service/message/data），等级由 `LOG_LEVEL` 控制，默认 ERROR；注意事项见 docs/RELIABILITY.md。

## 9. 测试体系（四层，2026-09-10 迁移后全量验证通过）

| 层级 | 位置 | 数量 | 验证内容 |
|------|------|------|---------|
| 单元 | tests/unit/ | 38（~2s） | 纯逻辑与抽象层，无外部 IO：DI 容器、配置、DDD 边界守护（AST 扫描）、回答策略、Database/VectorStore/LLM 端口契约、文档 Pipeline、TXT/PDF 解析器、健康检查 |
| 集成 | tests/integration/（除 API） | 52（~22s） | 真实 SQLite（SQLAlchemy 实现的持久化/外键级联/事务提交与回滚/建表幂等/旧库补列迁移/来源往返）、**排序契约（乱序落库后由服务层按时间排序 + 同时间稳定性）**、真实 Chroma（写入/检索/删除/持久化）、LLM Provider 协议（MockTransport）、Embedding 入库、RAG 检索、Agent 图（含流式走图）、对话服务 |
| 接口 | tests/integration/test_api.py | 8（~11s） | 完整应用（临时 SQLite/Chroma + Fake LLM，不启动真实服务）：会话 CRUD、统一错误结构、SSE 流式协议（delta/done + 持久化）、文档上传/删除/非法格式拒绝 |
| 端到端 | scripts/verify_real_e2e.py 等（手工运行） | 3 个脚本 | 真实 uvicorn + 真实 Ollama/embedding/Chroma：真实法律文档上传→向量化入库→流式 RAG 问答引用原文→消息持久化 |

数据：tests/data_source/ 为 RAG 测试数据源（真实法律文档：专利法 TXT + MD）。

- 自动化测试合计 98 个，`uv run pytest` 全量运行，无需任何外部服务（Fake/确定性实现遵循领域端口，与生产实现互换验证同一契约：InMemoryDatabase、DeterministicEmbedding、ScriptedLLM）。
- 端到端脚本依赖真实外部服务（本机 Ollama 模型、GLM 密钥），不纳入 pytest 自动化，保持自动化测试的封闭性与可重复性；运行方式见脚本头部说明，验证结论记录于 feature_list.json 各功能 evidence。

## 10. 扩展点与预留

- **MySQL 8.0**：表结构与 DML 已由 SQLAlchemy Core 统一（`infrastructure/database/sqlalchemy/`），接入只剩两步——安装异步驱动（`aiomysql`，纯 Python，Windows 无需编译）、在 `containers.py` 增加 `mysql+aiomysql://…` 的 URL 分支并启用 `DbProvider.MYSQL`；届时需补 MySQL 真实实例上的集成验证与迁移方案（Alembic 或等价机制）。
- **Milvus**：实现 `VectorStore` 端口替换骨架 `milvus.py`；`VECTOR_STORE_PROVIDER=milvus` 时装配成功、调用时明确报错（拒绝静默空结果）。
- **新文档格式**：实现 `DocumentParser` 策略并注册进 `DocumentParserFactory`。
- **新 LLM Provider**：实现 `LLMProvider`（chat + stream + model_name），容器工厂加分支；密钥仅环境注入。
- **新问答节点**：继承 `AgentNode`，在 `QaGraphBuilder.build()` 中接线。
- **前端**（FE-001 基础框架完成；FE-002~010 待开发）：遵循第 7 节 API 契约与 SSE 协议；开发期统一请求相对路径 `/api/...`，由 Vite 代理转发，前端代码不感知后端地址。
