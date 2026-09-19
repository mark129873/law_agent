# Law Agent

> 基于 LangGraph、Milvus 和 FastAPI 构建的法律助手 Agent。


> [!IMPORTANT]
> 本项目处于工程实践阶段；模型输出仅供参考，不构成法律意见，也不能替代执业律师的专业判断。


## 项目简介

Law Agent 意图构建法律助手，已完成知识库问答场景（法条检索），并通过 Tavily Remote MCP 提供可由用户显式开启的联网搜索；合同&文书审查、案件辅助等插件仍保留 Stub 入口，等待后续开发。

用户可以上传文档，系统完成文档解析、清洗、段落感知切分、向量化和 Milvus 入库；用户提问后，Agent 通过 LangGraph 主图与 Local Legal RAG 子图完成问题路由、本地 Legal RAG、依据校验与确定性收尾；检索走 Milvus 稠密向量 + BM25 混合召回（服务端 RRF），本地 Reranker 重排。回答必须能落到知识库来源；没有依据时会明确说明，而不是编造法条。

项目的重点不是简单地把检索结果拼接到 Prompt，而是将以下能力组合成一条可观测、可测试、可降级的 Agent 链路

![image](.github/images/mock3.webp)

## 技术栈

| 层 | 选型 |
| --- | --- |
| 前端 | React 19 · TypeScript（严格模式）· Vite 8 · Tailwind CSS v4 · React Router 7 |
| 后端 | Python 3.11 · FastAPI（全异步）· uv · LangGraph |
| 数据 | SQLAlchemy 2.0 Async + SQLite（当前启用；MySQL 预留端口） |
| 检索 | Milvus Cloud（默认）或 Milvus Standalone（dense + 稀疏 BM25，服务端 `hybrid_search` + RRF） |
| 模型 | Ollama 本地、智谱 GLM API 或 DeepSeek API；Embedding 默认 Ollama `nomic-embed-text` |
| 重排 | `cross-encoder/ms-marco-MiniLM-L-6-v2`（CrossEncoder）；关闭或失败时使用 RRF 序 |
| 观测 | 结构化 JSON 日志 + 可选 Langfuse 三级 trace |


Agent 编排: LangGraph 主图 + Local Legal RAG 子图；
- 主图负责意图路由、能力编排和收尾，实现“编排决策 → 执行 → 汇总观察结果 → 再次决策”, 实现受控、结构化的 ReAct 主循环, 通过 Grounding 校验反馈加入了 Reflection/自我纠错能力
- RAG 子图SubAgent负责检索策略与证据处理, 实行Plan-and-Execute, Planner选择原始问题、查询改写、子问题拆分、术语扩展等strategy，通过条件边fan-out并发执行混合检索
- 可观测性: Langfuse trace/span/generation结构化、JSON 日志、Request ID、节点耗时、LLM generation、 三级追踪
- 工程边界: API → Application → Domain；Infrastructure 和 Agent 实现DDD领域端口，统一由依赖装配点注入


## 系统架构

```text
Frontend (React)  --HTTP/SSE-->  FastAPI
                                      │
                    Application  →  Domain 端口
                                      ▲
                    Infrastructure    │    Agent (LangGraph)
                    SQLite / Milvus   │    主图 + legal_rag 子图
                 Ollama / GLM / DeepSeek│    Tavily MCP / Plugin Stub
```

### 主图流程

![image](.github/images/main_graph2.webp)

### RAG 子图流程

![image](.github/images/rag_subgraph.webp)

## 快速开始
### 环境要求
- Python `>=3.11`, 以及环境变量管理工具 [uv]
- Milvus Cloud Endpoint + API Key（默认）；或 Docker Desktop / Docker Compose（本地 standalone）
- Node.js 与 npm
- Ollama，或可访问的 GLM/DeepSeek API

### 1. 克隆项目并创建配置
```bash
git clone https://github.com/mark129873/law_agent_harness.git
cd law_agent_harness
cp backend/.env.example backend/.env
```
### 2. 配置 Milvus

默认连接 Milvus Cloud。在 `backend/.env` 中填写：

```dotenv
MILVUS_CLOUD_URI=https://<cluster-endpoint>
MILVUS_PROVIDER=cloud
MILVUS_CLOUD_TOKEN=<zilliz-api-key>
MILVUS_COLLECTION_NAME=law_chunks
```

`MILVUS_CLOUD_TOKEN` 使用 Zilliz Cloud API Key 原文，不要加 `Bearer`。`MILVUS_PROVIDER` 默认是 `cloud`，不会根据 URI 是否存在自动推断。

如需改用本地 standalone，设置 `MILVUS_PROVIDER=local`，再填写 `MILVUS_URI=http://127.0.0.1:19530` 和可选的 `MILVUS_TOKEN`，并启动：

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
脚本会完成模型下载和检验。

### 4. 配置并启动后端

```bash
cd backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```
若使用 Ollama：
```bash
ollama serve
ollama pull qwen3.5:4b
ollama pull nomic-embed-text:latest
```
若使用 GLM，设置 `LLM_PROVIDER=glm` 和 `GLM_API_KEY`；若使用 DeepSeek，设置 `LLM_PROVIDER=deepseek` 和 `DEEPSEEK_API_KEY`，默认模型为 `deepseek-chat`，思考模式固定关闭。


### 5. 启动前端
```bash
cd frontend
npm install
npm run dev
```
- 访问：<http://localhost:5173>

## RAG 评测

评测直接调用真实 `QaWorkflow`，根据测试问题、答案要点、检索证据和最终回答评估 RAG 生成质量。
复用当前后端配置的 Milvus 知识库、Embedding、Reranker 和 LLM；这些依赖可用且测试文档已入库后，
无需启动 HTTP 服务即可执行：

```bash
cd backend
uv run python scripts/evaluate_rag.py workflow --cases tests/evaluation/rag_cases.jsonl
```

数据集位于 `backend/tests/evaluation/rag_cases.jsonl`，包含问题、期望来源、答案要点和引用要求。
LLM Judge 对每条回答按 0–5 分评分：

| 维度 | 评估内容 |
| --- | --- |
| 正确性 | 回答是否符合问题和答案要点 |
| 完整性 | 是否覆盖主要答案要点 |
| 依据支持 | 回答中的事实是否有检索证据支撑 |
| 引用准确性 | 引用是否来自检索证据并与回答对应 |

Judge 通过条件为正确性 ≥4、完整性 ≥3、依据支持 ≥4；要求引用的案例还需引用准确性 ≥4。
报告同时记录 grounding 校验结果、基于来源文件名的引用精确率/召回率，
以及 Hit@K、Recall@K、MRR、耗时和失败案例，辅助定位生成质量问题。
Judge 可通过 `EVAL_JUDGE_PROVIDER` 与 `EVAL_JUDGE_MODEL` 独立配置，默认使用主 LLM。

如果当前知识库还没有数据集对应的测试文档，先按“快速开始”启动后端，再在另一个终端导入：

```bash
cd backend
uv run python scripts/evaluate_rag.py prepare --base-url http://127.0.0.1:8000
```

`prepare` 会向当前知识库追加测试文档；只有明确需要重建当前知识库时才使用
`prepare --reset`，该参数会删除当前 SQLite 数据库中的全部文档及其向量内容，不能当作普通评测前置步骤。

结果写入 `backend/log/evaluation/<run_id>/`：`report.json` 保存逐题回答、证据和 Judge 评分，
`report.md` 提供指标汇总与案例结果；原始报告不提交 Git。
命令成功退出表示报告已生成，回答质量是否达标应查看报告中的分数、通过率和失败案例。
历史脱敏基线见 [`docs/evaluation-baseline.md`](docs/evaluation-baseline.md)，不代表当前配置下的质量分数。

## 项目结构

```text
law_agent/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI 路由、DTO、异常处理
│   │   ├── application/      # 问答、会话、文档、知识库应用服务
│   │   ├── domain/           # 实体、Repository 和领域端口
│   │   ├── infrastructure/   # SQLite、Milvus、Ollama、GLM、DeepSeek、Langfuse 实现
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

## 许可证

本项目采用 [MIT License](LICENSE) 开源。
