# 会话交接

## 当前已验证
- 现在明确可用的部分：
  - **后端 BE-001~023 全部 passing**（含 BE-023：流式回答参考来源）。
  - **前端 FE-001~011 全部 passing**（含 FE-011：回答参考文档展示——2026-09-06 真实浏览器端到端验证通过）。
  - **测试体系**：后端自动化 92 个 + 端到端脚本 3 个 + 真实浏览器 E2E（headless Edge，脚本与截图在仓库外 Temp/opencode/fe011/）。
- 最近一轮实际跑过的验证（2026-09-06，Session 018）：
  - 后端 `uv run pytest` → 92 passed；前端 `npm run build`（tsc + vite）→ 通过
  - 真实浏览器 E2E 通过：RAG 有按钮（计数 4）→ 点开展示序号/文件名/命中内容 → 刷新重进仍在；空知识库无按钮；文档已恢复 ready，测试会话已清理

## 本轮改动
- 后端：QaStreamEvent 领域事件（qa_workflow.py）；RetrieveNode 推送 sources（nodes.py）；RagService 拆出纯函数 format_context（Prompt 上下文与参考来源同源）；ChatService 流式收集来源并持久化；ConversationService.add_message 增加 sources 参数；SQLite messages 表加 sources 列 + 幂等迁移（database.py）；dto/消息路由/SSE 路由映射 sources；verify_real_e2e.py 加断言
- 前端：types（ReferenceSource、Message.sources、ChatStreamEvent sources 分支）；chat.ts onSources 回调；AppContext done 时挂 sources；MessageBlock 参考文档折叠面板；index.css ref-panel-in 入场动画（prefers-reduced-motion 静止）
- 测试：test_api.py 新增 sources 流式+持久化用例与夹具修复（入库/检索统一确定性 embedding，此前维度不一致导致检索报错）；test_agent_graph.py 流式用例改事件断言+新增 2 例；test_sqlite_database.py 新增来源往返+旧库迁移 2 例；test_conversation_service.py 新增来源往返 1 例
- 文档：PRODUCT.md（参考文档交互两条）、ARCHITECTURE.md（数据流/SSE 协议/前端数据流）、feature_list.json（BE-023 passing、FE-011 in_progress）

## 仍损坏或未验证
- 已知缺陷：无
- 未验证路径：FE-011 浏览器端到端（本轮最后一 步执行）；深色主题未做强制暗色截图（token 与浅色同源镜像，风险低）；uvicorn 多 worker 并发；HTTPS/反向代理；CORS 生产收敛（当前 allow_origins=["*"]）
- 下一轮会话需要注意的风险：
  - Ollama 0.32.0 偶发缺陷：上传（embedding 批处理）后立即提问，/api/chat 可能返回 500（模型切换窗口，复现约 1/2）；后端已正确转为 SSE error 事件。如需彻底解决可在 OllamaProvider 加一次重试
  - 测试数据污染会退化检索质量（重复上传导致向量重复）：测试前按 RELIABILITY.md 重置 backend/data 并重启后端
  - Windows 下 TaskStop/taskkill 可能超时或留孤儿进程占用 8000：`netstat -ano | grep :8000` 找 PID 后用 PowerShell `Stop-Process -Force` 清理；Git Bash 偶发 `uv` 找不到（exit 127），重试即可
  - Ollama qwen3.5:4b 已默认关闭思考模式（LLM_ENABLE_THINKING=false）；开启后首字延迟回到 30~40s 量级
  - 浏览器 IAB 上传不走系统文件选择框：用页面内 DataTransfer 构造 File 派发 input change（FE-008/011 均此路径）
  - min_score 默认 0.0（不过滤）；E2E 脚本依赖本机 Ollama（qwen3.5:4b / nomic-embed-text:latest）与 .env 中 GLM_API_KEY

## 下一步最佳动作
- FE-011 已 passing；全项目 BE-001~023 + FE-001~011 无未完成项
- 可选增强方向（需用户决定）：会话重命名（需后端 PATCH 端点）、回答停止按钮（需后端取消协议）、深色主题手动开关、部署方案与 CORS 收敛、OllamaProvider 加重试（上传后立即提问偶发 500）
- 这一步中哪些东西不要动：后端 API 契约（ARCHITECTURE.md 第 7 节表格与 SSE 协议含 sources）；统一错误结构 {code,message}；前端 api/state 分层与主题 token 体系；messages.sources 的存储格式（JSON 数组 [{source,content}]）

## 命令
- 后端启动：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 后端验证：`cd backend && uv run pytest`（全量 92 个）；分层：`pytest tests/unit` / `pytest tests/integration`
- 前端构建：`cd frontend && npm install && npm run build`（tsc 类型检查 + vite）
- 前端启动：`cd frontend && npm run dev`（http://localhost:5173，/api 代理到后端 8000；联调需先启动后端）
- 端到端：启动服务器后 `PYTHONPATH=backend python backend/scripts/verify_real_e2e.py`（已含 sources 断言）
- 定向调试：`LOG_LEVEL=INFO uv run uvicorn app.main:app --port 8000`；OpenAPI http://127.0.0.1:8000/docs
