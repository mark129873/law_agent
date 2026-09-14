# Law Agent

> 基于 LangGraph、Milvus 和 FastAPI 构建的法律助手 Agent。


> [!IMPORTANT]
> 本项目处于工程实践阶段；模型输出仅供参考，不构成法律意见，也不能替代执业律师的专业判断。


## 项目简介

Law Agent 意图构建法律助手, 目前第一版已完成知识库问答场景(法条检索), 并预留插件入口(合同&文书审查插件、案件辅助插件)、外部知识补充(网页搜查、外接MCP)以待后续开发。

用户可以上传文档，系统完成文档解析、清洗、段落感知切分、向量化和 Milvus 入库；用户提问后，Agent 通过 LangGraph 主图与 Local Legal RAG 子图完成问题路由、本地 Legal RAG、依据校验与兜底；检索走 Milvus 稠密向量 + BM25 混合召回（服务端 RRF），本地 Reranker 重排。回答必须能落到知识库来源；没有依据时会明确说明，而不是编造法条。

项目的重点不是简单地把检索结果拼接到 Prompt，而是将以下能力组合成一条可观测、可测试、可降级的 Agent 链路

![image](.github/images/mock3.webp)

## 技术栈

| 层 | 选型 |
| --- | --- |
| 前端 | React 19 · TypeScript（严格模式）· Vite 8 · Tailwind CSS v4 · React Router 7 |
| 后端 | Python 3.11 · FastAPI（全异步）· uv · LangGraph |
| 数据 | SQLAlchemy 2.0 Async + SQLite（当前启用；MySQL 预留端口） |
| 检索 | Milvus Standalone（dense + 稀疏 BM25，服务端 `hybrid_search` + RRF） |
| 模型 | Ollama 本地 或 智谱 GLM API；Embedding 默认 Ollama `nomic-embed-text` |
| 重排 | `cross-encoder/ms-marco-MiniLM-L-6-v2`（CrossEncoder）；关闭或失败时使用 RRF 序 |
| 观测 | 结构化 JSON 日志 + 可选 Langfuse 三级 trace |


Agent 编排: LangGraph 主图 + Local Legal RAG 子图；
- 主图负责意图路由、能力编排和收尾，实现“编排决策 → 执行 → 汇总观察结果 → 再次决策”, 实现受控、结构化的 ReAct 主循环, 通过 Grounding 校验反馈加入了 Reflection/自我纠错能力
- RAG 子图SubAgent负责检索策略与证据处理, 实行Plan-and-Execute, Planner选择原始问题、查询改写、子问题拆分、术语扩展等strategy，通过条件边fan-out并发执行混合检索
可观测性: Langfuse trace/span/generation结构化、JSON 日志、Request ID、节点耗时、LLM generation、 三级追踪
工程边界: API → Application → Domain；Infrastructure 和 Agent 实现领域端口，统一由依赖装配点注入


## 系统架构

```text
Frontend (React)  --HTTP/SSE-->  FastAPI
                                      │
                    Application  →  Domain 端口
                                      ▲
                    Infrastructure    │    Agent (LangGraph)
                    SQLite / Milvus   │    主图 + legal_rag 子图
                    Ollama / GLM      │    Web/Plugin Stub
```

### 主图流程

![image](.github/images/main_graph.webp)

### RAG 子图流程

![image](.github/images/rag_subgraph.webp)

## 快速开始
### 环境要求
- Python `>=3.11`, 以及环境变量管理工具 [uv]
- Docker Desktop / Docker Compose
- Node.js 与 npm
- Ollama，或可访问的 GLM API

### 1. 克隆项目并创建配置
```bash
git clone https://github.com/mark129873/law_agent_harness.git
cd law_agent_harness
cp backend/.env.example backend/.env
```
### 2. 启动 Milvus
```bash
docker compose -f backend/docker-compose.yml up -d
```

### 3. 下载并验证 Reranker 模型

项目统一使用 `cross-encoder/ms-marco-MiniLM-L-6-v2`。首次使用需要联网从 Hugging Face 下载；检查脚本会把模型保存到仓库根目录的 `.model/cross-encoder/ms-marco-MiniLM-L-6-v2`，后续启动可以直接复用本地文件：

```bash
cd backend
uv sync
uv run python scripts/check_rerank_model/check_rerank_local.py
```

脚本会完成模型下载、CPU 加载和三条样本文档打分。`.model/` 已加入 `.gitignore`，模型文件不会提交到 Git。

### 4. 配置并启动后端

在 `backend/.env` 中确认使用脚本下载的本地模型：

```env
RERANK_ENABLED=true
RERANKER_MODEL_PATH=../.model/cross-encoder/ms-marco-MiniLM-L-6-v2
RERANKER_DEVICE=cpu
```

以上相对路径以 `backend` 目录为当前工作目录；也可以将 `RERANKER_MODEL_PATH` 改为该模型目录的绝对路径。GPU 环境可将 `RERANKER_DEVICE` 改为 `cuda`。如果暂时关闭精排，设置 `RERANK_ENABLED=false`，系统会明确显示“精排已关闭”；只有模型加载或推理失败才显示故障降级。
```bash
cd backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```
默认配置使用 Ollama：
```bash
ollama serve
ollama pull qwen3.5:4b
ollama pull nomic-embed-text:latest
```
如果使用 GLM，将 `backend/.env` 中的 `LLM_PROVIDER` 改为 `glm`，并设置 `GLM_API_KEY`。


### 5. 启动前端
```bash
cd frontend
npm install
npm run dev
```
- 访问：<http://localhost:5173>

## 项目结构

```text
law_agent/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI 路由、DTO、异常处理
│   │   ├── application/      # 问答、会话、文档、知识库应用服务
│   │   ├── domain/           # 实体、Repository 和领域端口
│   │   ├── infrastructure/   # SQLite、Milvus、Ollama、GLM、Langfuse 实现
│   │   ├── agent/             # LangGraph 主图、RAG 子图、Prompt、Agent 服务
│   │   └── containers.py      # 唯一依赖装配点
│   ├── tests/                 # unit / integration / API 测试
│   ├── scripts/               # Milvus 重置、真实 E2E 等脚本
│   ├── docker-compose.yml     # Milvus standalone 依赖
│   └── pyproject.toml
├── frontend/
│   ├── src/api/               # 统一 API 与 SSE 客户端
│   ├── src/state/             # React Context 状态
│   ├── src/pages/             # 对话页、知识库页
│   └── src/components/        # 通用 UI 组件
├── docs/
│   ├── ARCHITECTURE.md        # 架构、数据流、契约和测试体系
│   ├── PRODUCT.md             # 用户可见行为与产品边界
│   └── RELIABILITY.md         # 日志、观测和干净环境规范
└── README.md
```
