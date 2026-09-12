# Architecture

## 0. 简单描述
-本文档只描述**架构与实现**（分层、数据流、配置、契约、测试体系）；用户可见的行为需求见 docs/PRODUCT.md
-实现变更不得改变 PRODUCT.md 描述的用户可见行为；行为要变，先改 PRODUCT.md，再改实现
-后端使用python3.11.15, 使用uv进行环境管理,.venv是虚拟环境
-后端使用fastapi, 接口使用异步函数
-后端使用langraph, 大模型支持ollama本地部署以及使用glm的api, 
-数据库此版本支持sqlite3, 后续版本支持mysql8.0根据配置进行切换, 做好数据库接口层抽象
-数据库实现统一走 SQLAlchemy 2.0 async ORM（声明式模型 + Data Mapper 映射），SQLite 是当前唯一已启用的 Provider，MySQL 8.0 接入只需换 URL 与异步驱动
-向量数据库使用 Milvus（standalone 部署，backend/docker-compose.yml 编排 etcd + minio + milvus），稠密向量与稀疏 BM25 混合检索由 Milvus 服务端 hybrid_search 完成（BE-029），业务代码经 VectorStore 端口访问，不感知具体实现

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
      │ SQLite → MySQL │  │ Milvus（dense+sparse）│
      └────────────────┘  └────────────────┘
               │
               ▼
      ┌─────────────────────────────┐
      │ LLM：Ollama 本地 / GLM API  │
      └─────────────────────────────┘
```

技术栈：Python 3.11 + FastAPI（全异步）+ uv 环境管理 + LangGraph + SQLAlchemy 2.0 async ORM（声明式模型 + AsyncSession，当前挂 aiosqlite 驱动）+ Milvus（服务端 hybrid_search：稠密 + 稀疏 BM25，RRF 融合）+ httpx。
前端技术栈：React 19 + TypeScript（严格模式）+ Vite 8 + Tailwind CSS v4 + React Router 7 + 原生 Fetch（无 axios）。

## 2. 目录结构

```text
backend/
├── app/
│   ├── api/                    # API / Controller 层
│   │   ├── dto.py              # 请求/响应模型（pydantic）
│   │   ├── errors.py           # 统一 AppError 体系与全局异常处理器
│   │   ├── middleware.py       # RequestIdMiddleware（纯 ASGI，注入请求链路标识）
│   │   └── routes/             # conversations / chat / documents 路由
│   │
│   ├── application/            # Application 层：业务流程编排
│   │   └── services/
│   │       ├── chat_service.py          # 问答编排（会话持久化 + QaWorkflow 端口）
│   │       ├── conversation_service.py  # 会话生命周期与消息持久化
│   │       ├── document_pipeline.py     # 解析→清洗→段落感知切分（解析器工厂）
│   │       ├── document_service.py      # 文档元数据状态机 + 入库/删除
│   │       ├── knowledge_service.py     # Pipeline→Embedding→向量库+关键词索引 双写入库
│   │       └── rag_service.py           # 混合检索编排（服务端 RRF 融合）与上下文构建
│   │
│   ├── domain/                 # Domain 层：实体 + 端口（零技术依赖）
│   │   ├── entities/           # conversation / message / document / chunk / llm
│   │   ├── repositories/       # Database / Conversation / Message / Document / VectorStore / KeywordIndex / LLMProvider 端口
│   │   └── services/           # document_parser / embedding / qa_workflow 端口
│   │
│   ├── infrastructure/         # 基础设施实现（实现领域端口）
│   │   ├── database/sqlalchemy/ # SQLAlchemyDatabase（models.py 声明式 ORM 模型 / mappers.py 实体↔模型映射 / types.py 时区无损时间列 / database.py 端口实现）；方言无关，MySQL 预留靠 URL 切换
│   │   ├── vector_store/       # MilvusVectorStore（dense+sparse 单集合，服务端 hybrid_search）
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
│   ├── common/                 # 横切基础设施：di.py 轻量容器 / logging.py 结构化 JSON 日志（stdout + backend/log 落盘）
│   ├── config/settings.py      # 统一配置（pydantic-settings，相对路径锚定 backend/）
│   ├── containers.py           # 唯一依赖装配点（工厂 + 单例注册）
│   └── main.py                 # 应用入口（lifespan / CORS / 路由 / 异常处理）
│
├── tests/
│   ├── unit/                   # 单元测试：纯逻辑与抽象层，无外部 IO
│   ├── integration/            # 集成测试：真实 SQLite/Milvus（服务不可达时跳过）/MockTransport/完整应用
│   └── data_source/            # RAG 测试数据源（真实法律文档）
├── log/                        # 运行日志（app.log + 按天轮转，gitignore，启动自动创建）
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
| `ConversationRepository` / `MessageRepository` / `DocumentRepository` | domain/repositories/ | SQLAlchemyDatabase 内置仓库（ORM Session + Data Mapper，方言无关） |
| `VectorStore` | domain/repositories/vector_store.py | MilvusVectorStore（dense+sparse 单集合，服务端 hybrid_search，BE-029） |
| `LLMProvider` | domain/repositories/llm_provider.py | OllamaProvider / GLMProvider |
| `DocumentParser` | domain/services/document_parser.py | TextParser / PdfParser |
| `EmbeddingService` | domain/services/embedding.py | OllamaEmbeddingService |
| `QaWorkflow` | domain/services/qa_workflow.py | LangGraph 工作流（agent/，经 `create_qa_workflow` 工厂暴露） |

### ORM 使用约定（BE-025）
- **两套模型、一层映射**：表结构用声明式 ORM 模型（`models.py`，只属于 infrastructure），领域实体保持纯 dataclass；两者之间由 `mappers.py` 显式双向映射（Data Mapper 模式）。为什么必须有这层：领域层零技术依赖由 AST 守护测试强制执行，ORM 模型不可能同时充当领域实体；把它固定成一层后，字段漂移只会在一个文件里暴露。
- **仓储出口只返回领域实体**：ORM 模型不得越过 infrastructure 边界（`test_orm_contract.py` 有断言锁定），否则应用层会被 ORM 类型与其会话状态悄悄污染。
- **Session 配置**：`async_sessionmaker(expire_on_commit=False)` + 单个 `AsyncSession`（对应"进程级单连接"策略）。`expire_on_commit=False` 是异步 ORM 的必要设置：默认 `True` 会在 commit 后使属性过期，之后访问会触发同步刷新，在 asyncio 下抛 `MissingGreenlet`。
- **不定义 relationship**：消息永远按 `conversation_id` 显式查询，没有聚合内导航需求；不定义关系就没有异步懒加载（`MissingGreenlet`）风险，级联删除仍由表级 `ON DELETE CASCADE` 保证（策略：用不到的关系图能力不引入）。
- **更新语义**：文档状态更新用"取出模型→改属性"（保持 identity map 与数据库一致，代价是一次额外 SELECT）；消息按会话删除用批量 `delete()` 并显式 `synchronize_session="fetch"`（需要影响行数、避免 N+1 加载，同时防止 session 内残留已删除对象造成脏读）。
- **JSON 存储沿用 TEXT + `json.dumps(ensure_ascii=False)`**：不换用 SQLAlchemy `JSON` 类型，以保持与既有数据库文件逐字节一致的存储格式与中文可读性。

### 排序职责（BE-024）
- **产品要求出处**：三处列表顺序（侧边栏会话按创建时间正序、对话内消息按时间正序、知识库文档按上传时间倒序）是 PRODUCT.md 第 2/3 节的产品要求；本节说明该要求由哪一层实现、按什么依据判断——因此这些描述不再重复写在 PRODUCT.md 里。
- **仓储只负责读写，不负责排序**：三个 Repository 的 `list` / `list_by_conversation` 不再输出 SQL `ORDER BY`（原 `ORDER BY created_at ASC, rowid ASC` 依赖 SQLite 专有的 `rowid`，MySQL 无此概念）。
- **排序规则集中在应用服务层，且只按创建时间判断**：`ConversationService.list_conversations`（`created_at` 正序）、`ConversationService.get_messages`（`created_at` 正序）、`DocumentService.list_documents`（`created_at` 倒序）。交换任何数据库实现，排序行为不变。
- 同一 `created_at`（微秒级相同）的记录没有第二排序键：输出顺序由底层返回顺序决定，Python `sorted` 的稳定性保证同一份数据重复查询结果一致；不再引入"物理行号"这类存储耦合的兜底键。

### 合规守护
- 领域层禁止导入任何技术库（fastapi/httpx/pymilvus/sqlalchemy/aiosqlite/pypdf/langgraph/pydantic 等）与应用层。
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
- **所有 LLM 问答必须走图**：对外唯一问答入口是 SSE 流式接口（`ChatService.stream_answer` → `astream`），检索、Prompt 组装、模型调用只有一份实现；禁止在图外直连 LLMProvider 做问答。图引擎本身仍支持非流式执行（`ainvoke`，测试与脚本经 `run_qa` 使用），与流式执行同一节点实例。
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
- 入库即写单个 Milvus 集合：稠密向量由 EmbeddingService 生成后传入，稀疏 BM25 表示由 Milvus 服务端按 content 字段自动生成（BM25 Function），两路数据天然同源，不存在双写一致性问题。

### RAG 混合检索（BE-029，Milvus 服务端 hybrid_search）
```text
query ──┬─▶ embed_query ──────────────┐
        └─▶ 原始查询文本（服务端 jieba 分词）─┤
                                          ▼
        VectorStore.hybrid_search：一次调用同时发起两路检索
          ├─ 稠密请求：FLOAT_VECTOR（COSINE），带 min_score range 过滤
          └─ 稀疏请求：SPARSE_FLOAT_VECTOR（BM25 词面打分）
                     ▼
        Milvus 服务端 RRFRanker(k=60) 融合 → 直接返回融合后的 top_k
```
- **为什么混合**：向量检索擅长语义相似（问法不同、含义相近），但法条编号、专有名词等精确词面匹配是弱项；BM25 恰好补足词面精确召回。
- **融合在服务端**：`hybrid_search` + `RRFRanker(k=60)` 是 Milvus 原生能力——BM25 分数与余弦相似度量纲不同不可直接加权，RRF 只用排名、无需调权（k=60 为论文推荐值）；同一 chunk 两路同时命中排名叠加、天然靠前。
- **为什么从自研 BM25 索引迁移到 Milvus（BE-028 → BE-029）**：自研方案（jieba + rank_bm25 进程内索引 + JSON 快照）每次增删要全量重建索引，万级 chunk 以上不可持续；Milvus 稀疏向量服务端增量建索引，且省去双写编排、快照管理与自研融合代码。
- **min_score 语义保持**：仍只作用于稠密通道的相似度过滤（默认 0.0 不过滤），经 range search（radius）在服务端执行；融合后得分为 RRF 分数（量纲约 1/k 级别），不参与 min_score 过滤。
- `build_context` / `format_context` 行为不变：仍产出带【来源：文件名】标注的上下文，无命中返回空串，衔接"信息不足"策略；参考来源事件（sources）与 Prompt 上下文依然同源。
- **集合懒建**：Milvus 集合在首次 `add_chunks` 时按实际 embedding 维度创建（稠密维度跟随 embedding 模型，无需配置）；检索在集合不存在时返回空（空知识库语义）。
- **数据落点**：Milvus 数据由 standalone 容器持久化（docker volume），不在 `backend/data/`；干净环境重置除删除 `backend/data/` 外还需运行 `scripts/reset_milvus.py` 删除集合（见 RELIABILITY.md）。

## 5. Agent 工作流（LangGraph）

### 面向对象结构
- `AgentNode`（抽象基类）+ `RetrieveNode` / `GenerateNode`（命令模式）：`__call__` 使节点实例可直接注册进图，新增节点继承基类即可（多态）。
- `QaGraphBuilder`（建造者模式）：按是否有 RAG 装配不同拓扑，装配规则集中一处。
- `LangGraphQaWorkflow`（适配器模式）：显式继承并实现 `QaWorkflow` 领域端口，langgraph 引擎封在适配器之内。
- `create_qa_workflow(llm, rag=None)`：模块对外唯一入口（工厂），rag 为 None 时为基础工作流。

### 图拓扑（LangGraph 图的图形化表示）

由 `QaGraphBuilder.build()` 装配；`rag=None` 时为基础工作流（`START` 直连 `generate`）：

```text
RAG 工作流：

        START
          │
          ▼
    ┌───────────┐
    │ retrieve  │   RagService 检索 → 写状态 {context}；命中时推 sources 事件
    └─────┬─────┘
          ▼
    ┌───────────┐
    │ generate  │   组装 Prompt → LLM 流式生成 → 写状态 {answer, history}；逐 token 推 delta 事件
    └─────┬─────┘
          ▼
         END

基础工作流：START → generate → END
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
| `VECTOR_STORE_PROVIDER` | milvus（当前唯一已启用 Provider） | milvus |
| `LLM_PROVIDER` | ollama / glm | ollama |
| `LLM_ENABLE_THINKING` | true / false | false（关闭思考模式） |
| `MILVUS_URI` | — | http://127.0.0.1:19530 |
| `HOST` / `PORT` / `LOG_LEVEL` | — | 0.0.0.0 / 8000 / INFO |




- **思考模式开关（`LLM_ENABLE_THINKING`，默认 false）**：qwen3.5 / glm-4.5 等推理模型默认会先"思考"再回答，显著拉长首字延迟（真实环境曾达 30~40s）。关闭时 Ollama 请求携带 `think: false`、GLM 请求携带 `thinking: {"type": "disabled"}`；需要深度推理时可显式开启。

- **敏感配置**：`GLM_API_KEY` 等密钥只经环境变量或本地 `.env` 注入，禁止提交仓库、禁止写入日志。
- **路径锚定**：相对路径统一锚定到 `backend/`（`resolved_sqlite_db_path`），数据位置不随进程工作目录变化。
- **数据目录自动创建（BE-026）**：数据目录不存在时（例如按 RELIABILITY.md 的"测试干净环境管理"删除了 `backend/data/`）由数据库实现在建连接前创建 SQLite 文件的父目录。因此 `data/` 被清空后仍可直接启动，不需要人工先建目录；Milvus 数据不在此目录（由容器卷持久化）。
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
- 启动时 lifespan 自动：SQLite connect + init_schema（幂等建表）、Milvus connect + 集合 load（集合不存在时等首次入库懒建）；关闭时释放。
- **首次启动自愈（BE-026）**：`backend/data/` 不存在时无需人工创建——数据库实现在建连接前创建 SQLite 文件的父目录；Milvus 侧集合不存在时由首次入库懒建，均为幂等操作，重复启动安全。
- 日志：单行 JSON（timestamp/level/service/request_id/message/data），同时输出 stdout 与 `backend/log/app.log`（按天轮转、默认保留 30 天），等级由 `LOG_LEVEL` 控制，默认 INFO；每个 HTTP 响应带 `x-request-id`；注意事项见 docs/RELIABILITY.md。

## 9. 测试体系（四层，2026-09-12 BE-029 Milvus 迁移后全量验证通过）

| 层级 | 位置 | 数量 | 验证内容 |
|------|------|------|---------|
| 单元 | tests/unit/ | 50（~4s） | 纯逻辑与抽象层，无外部 IO：DI 容器、配置、DDD 边界守护（AST 扫描）、日志契约（落盘/轮转/脱敏/降级/幂等/request_id：BE-027）、回答策略、Database/VectorStore 混合检索契约（内存 Fake）/LLM 端口契约、文档 Pipeline、TXT/PDF 解析器、健康检查 |
| 集成 | tests/integration/（除 API） | 60（~35s） | 真实 SQLite（SQLAlchemy ORM 实现的持久化/外键级联/事务提交与回滚/建表幂等/旧库补列迁移/来源往返）、首次启动自愈（数据目录不存在时自动建库、干净环境重置后可再次启动：BE-026）、ORM 契约（出口只返回领域实体、`expire_on_commit=False` 提交后可读、identity map 更新一致、批量删除无脏读、回滚撤销属性更新）、排序契约（乱序落库后由服务层按时间排序 + 同时间稳定性）、**真实 Milvus 混合检索（稠密+稀疏双通道/RRF 融合/min_score range 过滤/按文档删除/跨连接持久化；服务不可达时跳过：BE-029）**、LLM Provider 协议（MockTransport）、Embedding 入库、RAG 检索、Agent 图（含流式走图）、对话服务 |
| 接口 | tests/integration/test_api.py | 9（~11s） | 完整应用（临时 SQLite + 内存 Fake 向量库 + Fake LLM，不启动真实服务）：会话 CRUD、统一错误结构、SSE 流式协议（delta/done + 持久化）、文档上传/删除/非法格式拒绝、x-request-id 生成与透传（BE-027） |
| 端到端 | scripts/verify_real_e2e.py 等（手工运行） | 3 个脚本 | 真实 uvicorn + 真实 Ollama/Milvus/LLM：真实法律文档上传→向量化入库→流式 RAG 问答引用原文→消息持久化；reset_milvus.py 供干净环境重置 |

数据：tests/data_source/ 为 RAG 测试数据源（真实法律文档：专利法 TXT + MD）。

- 自动化测试合计 119 个，`uv run pytest` 全量运行，无需任何外部服务（Fake/确定性实现遵循领域端口，与生产实现互换验证同一契约：InMemoryDatabase、InMemoryVectorStore、DeterministicEmbedding、ScriptedLLM）；**唯一例外**是 tests/integration/test_milvus_vector_store.py 需要真实 Milvus（docker compose up -d），服务不可达时自动跳过并在 reason 中注明。
- 端到端脚本依赖真实外部服务（本机 Ollama 模型、GLM 密钥），不纳入 pytest 自动化，保持自动化测试的封闭性与可重复性；运行方式见脚本头部说明，验证结论记录于 feature_list.json 各功能 evidence。

## 10. 扩展点与预留

- **MySQL 8.0**：表结构与 DML 已由 SQLAlchemy ORM 统一（`infrastructure/database/sqlalchemy/models.py` 声明式模型），接入只剩两步——安装异步驱动（`aiomysql`，纯 Python，Windows 无需编译）、在 `containers.py` 增加 `mysql+aiomysql://…` 的 URL 分支并启用 `DbProvider.MYSQL`；届时需补 MySQL 真实实例上的集成验证与迁移方案（Alembic autogenerate 可直接消费现有声明式模型）。
- **Milvus**（BE-029 已实现）：`MilvusVectorStore` 实现完整 VectorStore 端口——单一集合同时持有稠密向量（COSINE）与稀疏 BM25 向量，`hybrid_search` 经 `RRFRanker(60)` 服务端融合；部署由 `backend/docker-compose.yml`（etcd + minio + standalone）承载，`MILVUS_URI` 默认指向 `http://127.0.0.1:19530`。
- **新文档格式**：实现 `DocumentParser` 策略并注册进 `DocumentParserFactory`。
- **新 LLM Provider**：实现 `LLMProvider`（chat + stream + model_name），容器工厂加分支；密钥仅环境注入。
- **新问答节点**：继承 `AgentNode`，在 `QaGraphBuilder.build()` 中接线。
- **前端**（FE-001 基础框架完成；FE-002~010 待开发）：遵循第 7 节 API 契约与 SSE 协议；开发期统一请求相对路径 `/api/...`，由 Vite 代理转发，前端代码不感知后端地址。
