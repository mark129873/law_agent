# 会话交接

## 当前已验证

- 现在明确可用的部分：
  - 后端全部功能就绪（BE-001~022，仅 BE-010 的 GLM 真实调用待 API Key 补验）：SQLite/Chroma/Milvus 骨架、Ollama/GLM LLM、文档 Pipeline（TXT/PDF）、Embedding 入库、RAG 检索、LangGraph Agent（含法律回答策略）、对话服务、全部 REST/SSE API、统一异常体系。
  - 完整业务闭环已可用：上传文档→向量化入库→提问→检索→流式回答→历史持久化→删除清理。
- 这轮实际跑过的验证：
  - 测试已分层：tests/unit/（33，纯逻辑）+ tests/integration/（42，真实基础设施）
  - 全量 `uv run pytest` → 75 passed；启动 smoke 通过
  - 真实 RAG 端到端（nomic-embed-text + Chroma + qwen3.5:4b）：引用来源回答 + 无依据声明信息不足
  - 真实 uvicorn：POST /api/conversations、40401 统一结构、TXT 上传→ready、bad.exe→40001

## 本轮改动

- 新增了哪些代码或行为：
  - BE-014：application/services/rag_service.py（retrieve/build_context/min_score）
  - BE-015/016/017：agent/state.py、agent/graph.py、agent/prompts.py（LEGAL_SYSTEM_PROMPT）
  - BE-018：application/services/conversation_service.py
  - BE-019~021：api/dto.py、api/errors.py、api/routes/{conversations,chat,documents}.py、application/services/{chat_service,document_service}.py、main.py 全量改造（CORS/路由/异常处理器/可注入 settings）
  - BE-022：统一 AppError 体系；修复 extra 误用 LogRecord 保留字段导致 404→500 的缺陷
- 基础设施或 harness 发生了哪些变化：依赖新增 langgraph、python-multipart；docs/ARCHITECTURE.md 新增第 26-29 节

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：BE-010 GLM 真实调用（缺 GLM_API_KEY）；uvicorn 多 worker 并发；HTTPS/反向代理场景
- 下一轮会话需要注意的风险：
  - 前端（FE-001~010）完全未开始；CORS 当前 allow_origins=["*"]（开发态，生产需收敛）
  - curl 在 Git Bash 下发中文 JSON 有编码问题（测试 API 用 ASCII 或 TestClient）
  - min_score 默认 0.0（不过滤）；接入真实检索质量调优时需按 nomic 分数分布配置

## 下一步最佳动作

- 最高优先级未完成功能：FE-001 前端项目基础框架
- 为什么它是下一步：后端业务闭环已完成并有 75 个测试与真实启动验证，前端是产品可用的最后一块
- 什么结果才算 passing：React+TS+Vite+Tailwind 项目可启动可构建，能访问基础路由
- 这一步中哪些东西不要动：后端 API 契约（见 docs/ARCHITECTURE.md 第 29 节表格与 SSE 协议）；统一错误结构 {code,message}

## 命令

- 启动命令：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 验证命令：`cd backend && uv run pytest tests -q`
- 定向调试命令：`LOG_LEVEL=INFO uv run uvicorn app.main:app --port 8000`；OpenAPI 文档 http://127.0.0.1:8000/docs
