# 会话交接

## 当前已验证

- 现在明确可用的部分：
  - **后端全部完成**：BE-001~022 共 22 项全部 passing（含 BE-010 双 Provider 真实调用、BE-012 真实《专利法》数据复验）。完整业务闭环可用：上传文档→向量化入库→提问→检索→流式回答→历史持久化→删除清理。
  - **架构合规**：DDD 分层经 AST 机械扫描违例清零（7 个领域端口定义在 domain 层）；langgraph 封闭在 `app/agent/`（唯一隔离区，对外仅 `create_qa_workflow` 工厂）；所有 LLM 问答统一走 LangGraph 图（流式/非流式同一节点）。
  - **测试体系四层**：单元 37 + 集成 39 + 接口 7 = 83 个自动化测试（25s，无外部服务依赖）+ 端到端脚本 3 个（真实服务，手工运行）；DDD 边界守护（test_ddd_boundaries.py）随 pytest 持续校验分层规则。
- 这轮实际跑过的验证（最近一轮四层验证，2026-09-06）：
  - `tests/unit` → 37 passed；`tests/integration`（除 API）→ 39 passed；`test_api.py` → 7 passed
  - 端到端：真实《专利法》TXT+MD 上传（201/ready）→ 流式提问 → 回答"发明专利权的保护期限为二十年"并引用第四十二条原文 → user/assistant 消息持久化
  - 启动 smoke：`/api/health` → ok
  - feature_list.json 后端部分经 62 项声明机械审计全部吻合（审计脚本按用户决定已删除）

## 本轮改动（Session 012）

- 前端 feature 清单评审修订（feature_list.json，均未改变功能编号与状态）：
  - FE-008 补齐 PRODUCT.md 要求但清单遗漏的能力：侧边栏知识库管理切换入口、文档列表展示（名称/大小/状态）、文档删除（后端 GET/DELETE /api/documents 已支持）
  - FE-009 联调闭环补"文档删除"；FE-001 锚定 frontend/ 目录；FE-002 明确统一错误结构/SSE 事件类型定义与轻量状态管理（hooks/Context）
  - FE-003~007、FE-010 评审通过未改动：与 PRODUCT.md 交互需求、Codex 风格要求、后端 SSE 协议逐条吻合
- 基线复验：uv run pytest → 83 passed

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：uvicorn 多 worker 并发；HTTPS/反向代理；CORS 生产收敛（当前 allow_origins=["*"]）
- 下一轮会话需要注意的风险：
  - 前端（FE-001~010）完全未开始
  - curl 在 Git Bash 下发中文 JSON 有编码问题（测 API 用 ASCII 或 TestClient/httpx）
  - min_score 默认 0.0（不过滤）；检索质量调优需按 nomic 分数分布配置
  - E2E 脚本依赖本机 Ollama（qwen3.5:4b / nomic-embed-text:latest）与 .env 中 GLM_API_KEY

## 下一步最佳动作

- 最高优先级未完成功能：FE-001 前端项目基础框架
- 为什么它是下一步：后端 22 项功能完成、四层测试全绿、文档同步，前端是产品可用的最后一块
- 什么结果才算 passing：React+TS+Vite+Tailwind 项目可启动可构建，能访问基础路由
- 这一步中哪些东西不要动：后端 API 契约（ARCHITECTURE.md 第 7 节表格与 SSE 协议）；统一错误结构 {code,message}；DDD 分层与 langgraph 隔离区规则（有守护测试，违例会挂）

## 命令

- 启动命令：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 验证命令：`cd backend && uv run pytest`（全量 83 个）；分层：`pytest tests/unit` / `pytest tests/integration`
- 端到端：启动服务器后 `PYTHONPATH=backend python backend/scripts/verify_real_e2e.py`
- 定向调试：`LOG_LEVEL=INFO uv run uvicorn app.main:app --port 8000`；OpenAPI http://127.0.0.1:8000/docs
