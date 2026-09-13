# law_agent — 法律知识库问答助手

基于 LangGraph 的法律问答 Agent：上传法律文档构建知识库，用户提问后经「检索 → 重排 → 证据评估 → 回答生成 → 依据校验」全链路流式作答，回答附「参考文档」来源标注，全过程以「思考」块实时展示。

## 快速启动

```bash
# 后端（Milvus + API）
cd backend
docker compose up -d                # 或 docker start milvus-etcd milvus-minio milvus-standalone
uv sync                             # Python 3.11，创建 .venv
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# 前端
cd frontend
npm install && npm run dev          # http://localhost:5173（/api 代理到 8000）

# 测试
cd backend && uv run pytest tests -q
```

LLM 默认 Ollama 本地部署，可切 GLM API；Langfuse 链路追踪等开关见 `backend/.env.example`。

## 文档索引

| 文档 | 内容 |
|------|------|
| [docs/PRODUCT.md](docs/PRODUCT.md) | 用户可见行为与产品决策记录（D1~D12） |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构、数据流、API 契约、测试体系、Prompt 硬约束契约 |
| [docs/RELIABILITY.md](docs/RELIABILITY.md) | 日志规则、Langfuse、干净环境管理 |
| [docs/qa_graph.mmd](docs/qa_graph.mmd) | 问答图 Mermaid 拓扑（由脚本导出） |
| [docs/archive/](docs/archive/) | 历史冷存：进度分卷 + 一期技术设计稿 |
| progress.md / session-handoff.md / feature_list.json | 当前开发状态与交接（根目录） |
