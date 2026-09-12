# 会话交接

## 当前已验证
- 现在明确可用的部分：
  - **后端 BE-001~030 全部 passing**（BE-007 Chroma / BE-008 Milvus 骨架 / BE-028 自研 BM25 混合检索已置 deprecated）；**前端 FE-001~013 全部 passing**。
  - **测试体系**：后端自动化 139 个（2026-09-12 全绿）；其中 test_milvus_vector_store.py 5 例需要真实 Milvus（docker compose up -d），服务不可达时自动跳过，其余保持封闭性。
  - **Agent 已升级为统一 Plan-and-Execute 闭环（BE-030）**：plan（问题拆解子查询）→ retrieve（多子查询混合检索合并去重）→ generate → verify（规则档 + LLM judge groundedness）；verify 依据不足带建议回 plan、表达契约失败回 generate，预算 plan_runs≤2 / generate_runs≤2；SSE 协议新增 plan/regenerating 事件。
- 最近一轮实际跑过的验证（2026-09-12，Session 028，BE-030/FE-013 统一规划闭环）：
  - 干净环境（删 backend/data + reset_milvus.py）`uv run pytest tests -q` → **139 passed**（unit 62 / integration 68 / api 9）
  - 前端 `npm run build` 通过
  - 真实 E2E（GLM + 真实 Milvus + 专利法）：plan 事件 2 个真实子查询 → sources 6 条 → 规则档 contract 触发一次 regenerating → 第二轮正确引用第四十二条"二十年" → 持久化与 sources 一致

## 本轮改动（Session 028：BE-030 统一规划闭环 + FE-013 前端适配）
- **agent/nodes.py**：新增 PlanNode（planner.chat 输出 JSON 子查询，parse_sub_queries 纯函数容错，失败透传原问题；推 plan 事件）与 VerifyNode（规则档先行 + LLM judge 三态 verdict；parse_judge_verdict 纯函数；解析失败视为 pass；打回前推 regenerating 事件）；RetrieveNode 改为逐子查询检索合并；GenerateNode 支持 verify_feedback 修正指令
- **agent/graph.py**：QaGraphBuilder 统一闭环装配——retrieve 出边只保留条件边（空命中且预算未用尽 → replan），verify 条件边（grounding→plan / contract→generate / pass→END）；rag=None 时 plan→generate→verify
- **agent/state.py**：AgentState 新增 sub_queries/verify_verdict/verify_feedback/plan_runs/generate_runs
- **agent/prompts.py**：新增 PLANNER_SYSTEM_PROMPT 与 VERIFY_JUDGE_SYSTEM_PROMPT；build_messages 增加 feedback 修正段；build_plan_messages/build_verify_messages
- **rag_service.py**：新增 retrieve_queries（多子查询检索 + chunk 合并去重 + 截断 top6）
- **SSE 协议**（ARCHITECTURE §7）：plan {sub_queries} / regenerating 事件；事件顺序 plan→sources→delta→（regenerating 后重复 sources→delta）→done/error
- **chat_service/chat 路由**：regenerating 时重置 delta 聚合；plan/regenerating 透传
- **前端**：types 扩展事件 union；chat.ts onPlan/onRegenerating 可选回调；AppContext subQueries 状态与重生成清空逻辑；MessageBlock 生成中渲染「问题拆解」列表；ChatPage 传参
- **配置**：settings 新增 PlannerProvider 枚举（follow/ollama/glm）与 planner_model；containers._build_planner 工厂
- **测试**：新增 test_agent_parsing 13 例；test_agent_graph 重写 19 例（ScriptedLLM 按系统提示分流规划/判分/生成脚本）；test_api 适配 plan 事件；test_settings 补 LLM_PROVIDER delenv（pymilvus load_dotenv 副作用）
- **文档**：ARCHITECTURE §5 目标图（含回边与预算）/§6 配置/§7 协议/§9 计数 139；PRODUCT.md 第 3 节新增拆解展示与自动校验重生成行为；RELIABILITY service 清单补 agent；feature_list BE-030/FE-013 passing

## 仍损坏或未验证
- 已知缺陷：无
- 未验证路径：
  - MySQL 8.0 真实接入（驱动、URL 分支、真实实例集成测试）——只做到"方言无关 + 容器显式拒绝"
  - 连接池化（每请求一会话/连接）——当前仍是单会话
  - 浏览器 GUI E2E 本轮未截图验证（build 类型检查 + SSE 事件消费 + API 层 E2E 已验证）
  - Ollama LLM 路径的真实模型 E2E（Ollama 已恢复可用，但本轮 E2E 走 GLM 配置；图闭环行为由集成测试锁定）
  - 本地小模型作 judge 的判分质量未做专项评估（解析失败安全放行，不阻塞问答）
- 下一轮会话需要注意的风险：
  - **启动前置条件变化**：后端启动前 Milvus 必须可达（`cd backend && docker compose up -d`）；容器当前由另一项目目录（code1/milvus）创建的同名容器承载，backend/docker-compose.yml 与其配置一致，`docker compose up -d` 会因容器名冲突报错——直接 `docker start milvus-etcd milvus-minio milvus-standalone` 即可
  - **容器内存上限（2026-09-12，按 4GB WSL2 重新收紧）**：milvus 2GB / etcd 256MB / minio 256MB，合计 2.5GB ≈ VM 的 62%（docker-compose.yml 已定义，并已对运行中容器 docker update 热应用）；若 Milvus 因内存压力被 OOM kill，先检查知识库规模是否已超出 2GB 上限承载，必要时同步调大 .wslconfig 与 mem_limit；注意 WSL 配置改动需 `wsl --shutdown` 重启后才生效
  - **pymilvus import 副作用**：import pymilvus 会 load_dotenv 把 backend/.env 灌入进程环境；新增依赖或测试时注意环境变量污染（敏感配置与默认值测试已加 delenv 防御）
  - **LangGraph 条件边陷阱（本轮踩坑）**：同一节点的静态出边与条件边不能同时指向会写同一 state 键的节点（并发写冲突 InvalidUpdateError）；条件回边必须自带预算检查
  - **每次问答 LLM 调用 3~4 次**（plan 1 + generate 1~2 + judge 1）：Ollama 本地部署延迟明显增加（可 PLANNER_PROVIDER=glm 缓解规划环节）；**OllamaProvider 仍无重试**，下一轮最值得做的独立功能
  - **verify 规则档与 Prompt 强耦合**：来源引用检查依赖回答含"【来源："字面；改 Prompt 输出格式时必须同步 VerifyNode 规则
  - **Milvus 一致性契约**：生产代码所有 create/search 都显式 Strong，改动检索代码时勿去掉（否则触发 #50969 空结果误报）
  - **测试干净环境流程**：删 `backend/data/` + `uv run python scripts/reset_milvus.py`（两步都要）
  - 既有遗留项：MySQL 未启用、连接池未引入、min_score 默认 0.0、Git Bash curl 上传中文文件名乱码（用 httpx）
- 下一步最佳动作（需用户决定）：OllamaProvider 加重试/降级（统一 plan 后调用次数多，风险放大）；或可选产品增强（会话重命名 / 停止按钮 / 深色主题开关 / CORS 收敛）或 MySQL 8.0 接入
- 这一步中哪些东西不要动：后端 API 契约（第 7 节表格与 SSE 协议——本轮新增 plan/regenerating 为向后兼容扩展，既有 delta/sources/done/error 形状未变）；统一错误结构 {code,message}；前端 api/state 分层；messages.sources 存储格式；`IsoDateTime` ISO-8601 格式；领域层零技术依赖（pymilvus/langgraph 不得进入 domain，守护测试会拦）；langgraph 只允许 app/agent/ 导入；数据落点（SQLite 在 backend/data/，Milvus 在容器卷）；**Milvus 集合 schema 与 Strong 一致性**（BM25 Function 依赖 content 字段名）；**RRFRanker k=60 口径**；**verify 预算常量 MAX_PLAN_RUNS/MAX_GENERATE_RUNS**（防死循环的正确性边界，调整属行为变更需走测试）

## 命令
- Milvus 启动：`cd backend && docker compose up -d`（容器名冲突时：`docker start milvus-etcd milvus-minio milvus-standalone`）
- 后端启动：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 干净环境重置（RELIABILITY.md，两步）：删除 `backend/data/` + `uv run python scripts/reset_milvus.py`
- 后端验证：`cd backend && uv run pytest`（全量 119 个；Milvus 未启动时 5 例自动跳过）
- 数据落点确认：SQLite `backend/data/law_agent.db`；Milvus 集合 `law_chunks`（容器卷）
- 前端构建/启动：`cd frontend && npm install && npm run build` / `npm run dev`
- 端到端（需 Milvus + Ollama/GLM）：启动服务器后 `PYTHONPATH=backend python backend/scripts/verify_real_e2e.py`
- 定向调试：`LOG_LEVEL=INFO uv run uvicorn app.main:app --port 8000`；OpenAPI http://127.0.0.1:8000/docs
