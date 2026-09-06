# 会话交接

## 当前已验证
- 现在明确可用的部分：
  - **前端全部完成**：FE-001~010 共 10 项全部 passing（全项目 32 项功能全绿）。完整产品闭环：侧边栏对话/知识库双视图 → 新对话（延迟创建，以首句提问为标题）→ 流式问答（Markdown 渲染、来源标注、生成中禁切）→ 历史恢复 → 两步确认删除；知识库上传（点击/拖拽 + 格式大小预校验）→ 状态展示 → 即时可 RAG → 删除级联清理。
  - **后端全部完成**：BE-001~022 共 22 项全部 passing（含 BE-010 双 Provider 真实调用、BE-012 真实《专利法》数据复验）。完整业务闭环可用：上传文档→向量化入库→提问→检索→流式回答→历史持久化→删除清理。
  - **测试体系**：后端四层 83 个自动化测试（无外部服务依赖）+ 端到端脚本 3 个；前端每个功能均经真实浏览器验证（截图/采样序列/异常注入），FE-009 完成对话与知识库两大业务闭环联调。
- 最近一轮实际跑过的验证（2026-09-06）：
  - 后端 `uv run pytest` → 83 passed；前端 `npm run build`（tsc 类型检查 + vite）→ 通过
  - 浏览器：提问流式回答引用专利法第四十二条/劳动合同法六个月/消保法三倍赔偿（均为真实 RAG）；增量渲染采样 506→681→823；停后端发送出现 502 错误条；上传真实 MD 入库「可检索」；删除会话/文档刷新后不复活
  - 启动 smoke：`/api/health` → ok

## 本轮改动
- FE-001：frontend/ 独立项目（React 19 + TS 严格模式 + Vite 8 + Tailwind v4 + Router 7，全源码中文注释）；vite 代理 /api → 8000；修复 TS7 CSS 副作用导入（vite-env.d.ts）
- FE-002：types/api/state 三层——client.ts request<T>+ApiError（统一错误 {code,message}）、conversations/documents/health/chat 五模块（chat.ts 用 fetch 消费 SSE，EventSource 不支持 POST）、AppContext 轻量全局状态（UI 组件零直接 fetch，grep 机械校验）
- FE-003：Codex 风格 Shell——语义化主题 token（stone 暖灰 + 唯一 emerald 强调色，明暗双主题跟随系统）、对话/知识库分段切换、图标统一 @phosphor-icons/react
- FE-004：对话页（欢迎空状态 + 建议问题 + 自适应输入 + Enter 发送）+ 流式发送；新会话延迟创建（title=提问截短 20 字，弥补后端不自动改标题）
- FE-005/006：会话切换消息恢复；删除两步确认 + danger 语义色 token
- FE-007：streamingRef 守卫生成中禁止切换/新建；增量渲染与异常路径实测验证
- FE-008：知识库页——上传面板（点击/拖拽、accept 限制、格式/大小前端预校验）、状态徽标、两步确认删除、utils/format
- FE-009：浏览器联调双闭环（对话闭环 + 知识库闭环含新文档即时 RAG）
- FE-010：react-markdown 渲染助手回答（默认不解析原始 HTML）；ink-faint 对比度达 WCAG AA（明暗两套）
- 文档同步：ARCHITECTURE.md（前端技术栈/目录树/数据流/启动验证/扩展点）、PRODUCT.md（延迟建会话交互）、init.md（前端验证路径）、feature_list.json（FE-002~010 逐项 evidence）

## 仍损坏或未验证
- 已知缺陷：无
- 未验证路径：深色主题未做强制暗色截图（token 与浅色同源镜像，风险低）；uvicorn 多 worker 并发；HTTPS/反向代理；CORS 生产收敛（当前 allow_origins=["*"]）
- 下一轮会话需要注意的风险：
  - Ollama 0.32.0 偶发缺陷：上传（embedding 批处理）后立即提问，/api/chat 可能返回 500（模型切换窗口，复现约 1/2）；后端已正确转为 SSE error 事件，前端展示错误条。如需彻底解决可在 OllamaProvider 加一次重试
  - 测试数据污染会退化检索质量（重复上传导致向量重复）：测试前按 RELIABILITY.md 重置 backend/data 并重启后端
  - Windows 下 TaskStop/taskkill 可能超时或留孤儿进程占用 8000（表现为旧代码仍生效或诡异 500）：`netstat -ano | grep :8000` 找 PID 后用 PowerShell `Stop-Process -Force` 清理；Git Bash 偶发 `uv` 找不到（exit 127），重试即可
  - Ollama qwen3.5:4b 已默认关闭思考模式（LLM_ENABLE_THINKING=false）；开启后首字延迟会回到 30~40s 量级
  - 流式过程中未闭合的 Markdown 标记会短暂显示字面字符（完成后正常渲染）
  - 前端依赖很新（Vite 8 / TS 7 / React 19 / react-markdown），生态兼容问题留意
  - min_score 默认 0.0（不过滤）；E2E 脚本依赖本机 Ollama（qwen3.5:4b / nomic-embed-text:latest）与 .env 中 GLM_API_KEY

## 下一步最佳动作
- 全项目 32 项功能全部 passing，无最高优先级未完成功能
- 可选增强方向（需用户决定）：会话重命名（需后端新增 PATCH 端点）、回答停止按钮（需后端取消协议）、深色主题手动开关、部署方案与 CORS 收敛
- 这一步中哪些东西不要动：后端 API 契约（ARCHITECTURE.md 第 7 节表格与 SSE 协议）；统一错误结构 {code,message}；前端 api/state 分层与主题 token 体系

## 命令
- 后端启动：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 后端验证：`cd backend && uv run pytest`（全量 83 个）；分层：`pytest tests/unit` / `pytest tests/integration`
- 前端构建：`cd frontend && npm install && npm run build`（tsc 类型检查 + vite）
- 前端启动：`cd frontend && npm run dev`（http://localhost:5173，/api 代理到后端 8000；联调需先启动后端）
- 端到端：启动服务器后 `PYTHONPATH=backend python backend/scripts/verify_real_e2e.py`
- 定向调试：`LOG_LEVEL=INFO uv run uvicorn app.main:app --port 8000`；OpenAPI http://127.0.0.1:8000/docs
