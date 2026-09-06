# 会话交接

## 当前已验证
- 现在明确可用的部分：
  - **前端基础框架（FE-001）已就绪**：frontend/ 独立项目（React 19 + TS 严格模式 + Vite 8 + Tailwind v4 + React Router 7）；`npm run build`（类型检查+打包）、`npm run dev`（5173 端口，/api 代理到后端 8000）均已真实验证通过；pages/api/components/types 目录结构就位，后续 FE 直接在上面叠加。
  - **后端全部完成**：BE-001~022 共 22 项全部 passing（含 BE-010 双 Provider 真实调用、BE-012 真实《专利法》数据复验）。完整业务闭环可用：上传文档→向量化入库→提问→检索→流式回答→历史持久化→删除清理。
  - **架构合规**：DDD 分层经 AST 机械扫描违例清零（7 个领域端口定义在 domain 层）；langgraph 封闭在 `app/agent/`（唯一隔离区，对外仅 `create_qa_workflow` 工厂）；所有 LLM 问答统一走 LangGraph 图（流式/非流式同一节点）。
  - **测试体系四层**：单元 37 + 集成 39 + 接口 7 = 83 个自动化测试（25s，无外部服务依赖）+ 端到端脚本 3 个（真实服务，手工运行）；DDD 边界守护（test_ddd_boundaries.py）随 pytest 持续校验分层规则。
- 这轮实际跑过的验证（最近一轮四层验证，2026-09-06）：
  - `tests/unit` → 37 passed；`tests/integration`（除 API）→ 39 passed；`test_api.py` → 7 passed
  - 端到端：真实《专利法》TXT+MD 上传（201/ready）→ 流式提问 → 回答"发明专利权的保护期限为二十年"并引用第四十二条原文 → user/assistant 消息持久化
  - 启动 smoke：`/api/health` → ok
  - feature_list.json 后端部分经 62 项声明机械审计全部吻合（审计脚本按用户决定已删除）


## 本轮改动
- 新增 frontend/ 独立项目：手写脚手架（全源码中文注释），index.html→main.tsx（BrowserRouter）→App.tsx 集中路由表→pages/HomePage 占位页
- Tailwind CSS v4（@tailwindcss/vite，无配置文件）；vite.config.ts 配置 /api 代理到 127.0.0.1:8000，前端代码只用相对路径
- 修复 TS7 对 CSS 副作用导入的 TS2882（补标准 vite-env.d.ts）；build = tsc --noEmit && vite build
- 验证证据：build 通过 / dev 292ms ready / curl / 200 / 代理 /api/health 返回 ok（后端日志确认）/ dist CSS 含 Tailwind 工具类
- 文档同步：ARCHITECTURE.md（前端技术栈、frontend/ 目录树、启动验证、扩展点状态）、init.md（前端验证路径）、feature_list.json（FE-001→passing）


## 仍损坏或未验证
- 已知缺陷：无
- 未验证路径：uvicorn 多 worker 并发；HTTPS/反向代理；CORS 生产收敛（当前 allow_origins=["*"]）
- 下一轮会话需要注意的风险：
  - 前端 FE-002~010 未开始（FE-001 框架已就绪，后续按清单叠加）
  - curl 在 Git Bash 下发中文 JSON 有编码问题（测 API 用 ASCII 或 TestClient/httpx）
  - min_score 默认 0.0（不过滤）；检索质量调优需按 nomic 分数分布配置
  - E2E 脚本依赖本机 Ollama（qwen3.5:4b / nomic-embed-text:latest）与 .env 中 GLM_API_KEY
  - 前端依赖很新（Vite 8 / TS 7），如遇生态兼容问题可降级到 Vite 5/6 + TS 5 稳定组合

## 下一步最佳动作
- 最高优先级未完成功能：FE-002 前端 API 与状态基础层
- 为什么它是下一步：所有页面（对话/历史/知识库）都依赖统一 API Service 与类型定义
- 什么结果才算 passing：页面通过统一 API Service 与后端通信，不在 UI 组件中散落 API 请求逻辑；类型定义覆盖会话/消息/文档/统一错误结构/SSE 事件
- 这一步中哪些东西不要动：后端 API 契约（ARCHITECTURE.md 第 7 节表格与 SSE 协议）；统一错误结构 {code,message}；FE-001 已建立的目录结构与代理配置

## 命令
- 后端启动：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 后端验证：`cd backend && uv run pytest`（全量 83 个）；分层：`pytest tests/unit` / `pytest tests/integration`
- 端到端：启动服务器后 `PYTHONPATH=backend python backend/scripts/verify_real_e2e.py`
- 前端构建：`cd frontend && npm install && npm run build`
- 前端启动：`cd frontend && npm run dev`（http://localhost:5173，联调需先启动后端）
- 定向调试：`LOG_LEVEL=INFO uv run uvicorn app.main:app --port 8000`；OpenAPI http://127.0.0.1:8000/docs
