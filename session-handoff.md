# 会话交接

## 当前已验证
- 现在明确可用的部分：
  - **后端 BE-001~027 全部 passing**；**前端 FE-001~012 全部 passing**。
  - **测试体系**：后端自动化 117 个（2026-09-11 全绿）；端到端脚本 3 个（依赖本机 Ollama，手工运行）。
- 最近一轮实际跑过的验证（2026-09-11，Session 025，删除非流式死代码 + §5 图拓扑图形化）：
  - 干净环境（先删 `backend/data`）`uv run pytest tests -q` → **117 passed**
  - 真实启动 smoke（8012 端口）：启动日志链正常、`/api/health` ok、`/api/conversations` 返回 `[]`；验证后进程已清理
  - 端到端（clean-state-checklist 新增要求）：**E2E PASS（GLM Provider 路径）**——RAG 回答正确引用专利法第四十二条"二十年"、sources 事件契约与持久化一致；本机 Ollama 的 llama-server 进程崩溃（0xc0000409 栈溢出，直接 curl 亦 500）无法走 Ollama 路径，属模型服务侧故障，与本轮改动无关

## 本轮改动（Session 025）
- **删除 `ChatService.send_message`（backend/app/application/services/chat_service.py）**：核实其在路由/测试/脚本中零调用（对外唯一问答端点是 `POST /api/chat/stream`），属死代码；且其内部不持久化 assistant 回答、丢失 sources，与流式路径行为漂移
- 保留 `QaWorkflow.ainvoke` 端口与 `graph.py` 的 `run_qa`/`build_qa_graph`（test_agent_graph.py 经它们非流式测图，属图引擎能力而非业务接口）
- **ARCHITECTURE.md**：§4"流式与非流式"表述改写（对外唯一入口是 SSE 流式接口）；§5"拓扑"小节改为图形化 LangGraph 图（retrieve → generate 节点流转 + 单行职责注记，含基础工作流退化形态），按用户要求保持简洁
- chat_service.py 模块 docstring 与行内注释同步
- feature_list.json 无功能状态变化（本轮为死代码清理与文档同步），JSON 校验通过

## 仍损坏或未验证
- 已知缺陷：无
- 未验证路径：
  - MySQL 8.0 真实接入（驱动、URL 分支、真实实例集成测试、增量迁移方案）——只做到"方言无关 + 容器显式拒绝"，无任何 MySQL 实机验证
  - 连接池化（每请求一会话/连接）——当前仍是单会话，端口形状与池化模型不兼容，属独立改造
  - 前端本轮未改动（未重跑 `npm run build`；API 契约与 SSE 协议未变）
  - 浏览器 E2E 本轮未执行；E2E 脚本 verify_real_e2e.py 本轮以 GLM Provider 等价流程验证通过（脚本本身未改，仍硬编码 Ollama 场景口径）
- 下一轮会话需要注意的风险：
  - **本机 Ollama 0.32.0 llama-server 进程崩溃未恢复**（原"上传后偶发 500"恶化为持续 500，直接 curl /api/chat 亦失败）：下轮如需 Ollama 路径，先重启 Ollama 服务并补验；紧急验证可用 `LLM_PROVIDER=glm` 启动后端（.env 已有 GLM_API_KEY）
  - **测试干净环境流程**（RELIABILITY.md）：开工/收尾测试前删除 `backend/data/`（启动时自动重建，BE-026；本轮 smoke 已再次验证自愈）
  - **ORM 新增的维护面**（已有 6 个契约测试锁住）：实体与 ORM 模型两套定义；session 状态语义；异步 ORM 必须保持 `expire_on_commit=False`，否则抛 `MissingGreenlet`
  - 同一 `created_at` 无第二排序键（用户指定"仅按时间判断"）
  - Ollama 0.32.0 偶发缺陷仍在：上传（embedding 批处理）后立即提问可能 500（后端已转为 SSE error 事件）
  - Windows 下 TaskStop/taskkill 可能超时或留孤儿进程占用端口：`netstat -ano | grep :PORT` 找 PID 后用 taskkill //PID //F；**Git Bash 的 `kill` 杀不掉 Windows PID 的监听进程**（本轮踩坑：新 uvicorn 绑定失败静默退出，旧进程继续服务造成误判）；Git Bash 偶发 `uv` 找不到（exit 127），重试即可
  - min_score 默认 0.0（不过滤）；E2E 脚本依赖本机 Ollama（qwen3.5:4b / nomic-embed-text:latest）与 .env 中 GLM_API_KEY

## 下一步最佳动作
- 若继续做数据库方向：MySQL 8.0 接入（`uv add aiomysql` → `containers.py` 增加 `mysql+aiomysql://…` URL 分支 → 真实实例跑同一批契约测试 → Alembic autogenerate 可直接消费现有声明式模型），属独立功能，需在 feature_list.json 立项
- 可选产品增强（需用户决定）：会话重命名（需 PATCH 端点）、回答停止按钮（需取消协议）、深色主题手动开关、部署方案与 CORS 收敛、OllamaProvider 加重试
- 这一步中哪些东西不要动：后端 API 契约（ARCHITECTURE.md 第 7 节表格与 SSE 协议含 sources）；统一错误结构 {code,message}；前端 api/state 分层与主题 token 体系；messages.sources 的存储格式（JSON 数组 [{source,content}]）；`IsoDateTime` 的 ISO-8601 存储格式（改了会让旧库时间无法回读）；领域层零技术依赖（ORM 模型不得进入 domain，守护测试会拦）；**数据存放位置**（用户明确要求保持 `backend/data/`，不要改锚点或写死绝对路径）

## 命令
- 后端启动：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 干净环境重置（RELIABILITY.md 规定，测试前后各做一次）：删除 `backend/data/`（启动时会自动重建，BE-026）
- 后端验证：`cd backend && uv run pytest`（全量 117 个）；分层：`pytest tests/unit` / `pytest tests/integration`
- 数据落点确认：`Get-ChildItem backend\data -Force`（应看到 `law_agent.db` 与 `chroma\`）
- 前端构建：`cd frontend && npm install && npm run build`（tsc 类型检查 + vite）
- 前端启动：`cd frontend && npm run dev`（http://localhost:5173，/api 代理到后端 8000；联调需先启动后端）
- 端到端（需本机 Ollama）：启动服务器后 `PYTHONPATH=backend python backend/scripts/verify_real_e2e.py`
- 定向调试：`LOG_LEVEL=INFO uv run uvicorn app.main:app --port 8000`；OpenAPI http://127.0.0.1:8000/docs
