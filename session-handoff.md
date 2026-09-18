# 会话交接

## Session 048：测试数据同步与真实 RAG 基线（2026-09-18）

### 本轮已完成
- 同步用户删除的两份测试文本：评测案例从 24 条调整为 23 条；真实 E2E 脚本不再引用已删除专利法 Markdown；pytest 数据集测试校验所有 expected source 文件真实存在。
- 使用 5 份当前测试文档导入独立 Milvus 集合 `law_agent_eval`。
- 真实 workflow 报告：`20260918T132908Z-cabbe758`，23 条中 10 条完成、13 条因 GLM `ConnectError`/HTTP 400 失败；完成样本 Hit@5 90%、MRR 0.8333。
- API/SSE 冒烟最近一次 2/2 通过：`api-smoke-20260918T133249Z-0ddb95`。
- 新增脱敏摘要 `docs/evaluation-baseline.md`，并同步 README、feature_list、progress。

### 验证与结论
- Milvus 恢复后 `uv run pytest tests -q -rs`：254 passed、1 warning；评测单测 12 passed。
- `compileall`、CLI help、`npm run build`、`git diff --check` 通过。
- BE-049 仍为 `in_progress`：检索完成样本可形成基线，但模型调用失败率过高，不能把本次结果标为质量门禁通过。

## Session 047：跳过 Milvus 的离线收尾（2026-09-18）

### 本轮已完成
- 按用户要求关闭 Docker Desktop；不删除容器、镜像或卷，也不执行恢复出厂。
- 在不依赖 Milvus 的前提下完成评测模块验证：评测单测 12 passed，全量后端 249 passed、5 skipped、1 warning。
- `compileall`、评测 CLI help、`frontend/npm run build`、`git diff --check` 均通过。

### 当前状态
- BE-049 代码与离线验证已完成，真实 `QaWorkflow` / Milvus / Embedding / LLM / Judge 基线尚未生成。
- 继续执行真实评测前，需先恢复 Docker/Milvus；完成后再运行下方 Session 046 的 `prepare → workflow → api-smoke`。

## Session 046：RAG 评测演示文档与双入口运行器（2026-09-18）

### 本轮已完成
- 新增 `backend/tests/evaluation/rag_cases.jsonl`，共 23 条案例：本地事实、多条件、证据不足、对抗前提和 direct control；已移除已删除的 `民事诉讼法2021.md` 对应案例。
- `QaWorkflow` 已在 `app/containers.py` 统一注册，ChatService 与评测器复用同一工作流；Milvus 集合名支持 `MILVUS_COLLECTION_NAME`，评测默认要求 `law_agent_eval*` 隔离集合。
- 新增 `app/evaluation/`：JSONL 校验、Recall/Hit@K、MRR、引用精确率/召回率、grounding/状态匹配、节点耗时、脱敏错误、结构化 LLM Judge、JSON/Markdown 报告。
- 新增 `scripts/evaluate_rag.py`：`prepare` 通过文档 API 重置并导入当前 5 份测试文档；`workflow` 直调真实 QaWorkflow；`api-smoke` 验证真实 HTTP/SSE 事件顺序、来源持久化和错误边界。
- 文档定位统一为 RAG 评测演示文档，已同步 `README.md`、`docs/ARCHITECTURE.md`、`docs/PRODUCT.md`、`docs/RELIABILITY.md`、`.env.example`。

### 本轮验证与未完成
- 首次 `uv run pytest tests -q -rs`：246 passed、5 skipped（Milvus 不可达）、1 warning；后续离线收尾全量结果为 249 passed、5 skipped、1 warning。
- `uv run pytest tests/unit/evaluation -q -rs`：12 passed；`compileall`、CLI help、`git diff --check` 通过。
- 使用 `MILVUS_COLLECTION_NAME=law_agent_eval` 尝试真实 workflow，初始化阶段因 `127.0.0.1:19530` 无法连接失败；没有生成或填写虚构的 RAG 基线分数。
- BE-049 仍为 `in_progress`。启动 Docker/Milvus、Embedding/LLM、Reranker 后，按 README 执行 `prepare → workflow → api-smoke`，确认报告内容后再改为 `passing`。

### 下一轮直接执行
```powershell
cd backend
$env:MILVUS_COLLECTION_NAME="law_agent_eval"
$env:SQLITE_DB_PATH="data/law_agent_eval.db"
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
uv run python scripts/evaluate_rag.py prepare --base-url http://127.0.0.1:8000 --reset-eval
uv run python scripts/evaluate_rag.py workflow --cases tests/evaluation/rag_cases.jsonl
uv run python scripts/evaluate_rag.py api-smoke --base-url http://127.0.0.1:8000
```

## 当前已验证
- 现在明确可用的部分：
  - **Agent 模块一期重写 + 思考块 + Langfuse trace + 全量 Prompt 优化 + 精排状态语义修复 + Reranker 模型统一 + 低质量兜底 Agent 删除 + Tavily Remote MCP 搜索全部 passing（BE-032~048 + FE-001~017；BE-030 deprecated）**：主图含 14 个业务节点 + RAG 子图 10 节点 + Tavily Web Search + Plugin Stub + 服务层 + status/think 双事件 + 豆包式思考块 + Langfuse 三级追踪 + 12 个 Prompt 五段结构化；grounding 预算耗尽直接确定性收尾。BE-049 评测运行器已实现但真实基线待补。
  - **Tavily Remote MCP 搜索（BE-048/FE-017）**：按钮状态通过 `use_web_search` 传递；`WebSearchPort` → Tavily Streamable HTTP `tavily_search` → `observation_node` → Answer/grounding/final；只在按钮开启时实际联网，搜索结果以 300 字网页预览经 `web_sources` 展示，完整原始/规范化数据写入 `backend/log/web_search/search-<UTC>-<UUID>.log`，落盘失败 fail-closed；真实 Remote MCP 已返回 5 条来源并完成 SSE/持久化验收。
  - **全量 Prompt 优化（BE-044，本轮新增）**：12 个 Prompt 统一五段结构（角色/任务/格式/规则/纪律）+ JSON 纪律（禁 markdown 代码块）+ 示例值防锚定标注 + answer_generator 明确【来源：文件名】格式硬约束 + grounding 降误判（实质一致即可/无关数字不算法律数据/宁可放行）。**编排器"不 finish"误诊修正**（Langfuse 时间线取证：闲聊打回真凶是重复执行 direct_answer，非 judge）——regenerating：RAG 2→0、闲聊 3→0；RAG 回答从 65 字重复堆砌变一句精准+来源标注。
  - **Langfuse trace（BE-043，本轮新增）**：domain TraceSink/TraceSpan 端口 + trace_sink_var（ContextVar）；infrastructure/trace/langfuse_sink.py（langfuse 4.15.2）；ChatService 记 trace 生命周期与流程事件、with_node_status 压/弹节点 span（子图嵌套）、LLMService 三路径记 generation；.env 开关 LANGFUSE_ENABLED（默认 false，缺密钥 WARN 降级，全方法吞异常）。
  - **真实云端验证通过**（jp.cloud.langfuse.com，用户 .env 预置密钥）：E2E trace 含 29 节点 span / 11 generation（model+Prompt+输出）/ 15 think + 2 regenerating 事件。
  - **精排状态语义修复（BE-045）**：`RERANK_ENABLED=false` 被识别为主动关闭，使用 RRF 但不再显示“精排不可用”；CrossEncoder 真失败仍保留 degraded/WARN；启动日志记录 `rerank_enabled` 与 `reranker_device`。
  - **Reranker 模型统一（BE-046）**：生产配置、检查脚本、`.env.example`、README 和架构文档统一为 `cross-encoder/ms-marco-MiniLM-L-6-v2`；检查脚本下载到根目录 `.model` 后从本地目录加载并执行样本打分。
  - **测试体系**：自动化 254 个；本轮评测单测 12 个，`test_milvus_vector_store.py` 5 例本轮已实际执行。
- 最近一轮实际跑过的验证（2026-09-16，Session 045 补充）：
  - Docker/Milvus 可用时全量 `uv run pytest tests -q -rs` → **242 passed, 1 warning**；5 个 Milvus 用例均实际执行。
  - `frontend/npm run build` → **tsc + Vite 构建通过**；`git diff --check` 与 `feature_list.json` JSON 校验通过。
  - 真实 Tavily SSE E2E：状态接口返回 `configured=true`；真实 `tavily_search` 返回 5 条来源，`web_sources→delta→done`、来源持久化、完整 JSON 日志和无 Authorization/Key 泄漏断言通过；按钮关闭时返回 `WEB_SEARCH_NOT_ENABLED` 且无远程调用/新日志。
  - 真实 RAG E2E：`scripts/verify_real_e2e.py` 上传 TXT/MD 均 `201 ready`，真实 Milvus/GLM 流式回答含“二十年”和专利法来源，sources 持久化一致；测试会话和新增测试文档已清理。
  - 既有后端/前端启动路径未改变：`backend` 仍按 Docker + uvicorn 启动，`frontend` 仍按 Vite 启动；本轮 1 个永久搜索日志已保留且未进入 Git；CUA 浏览器 inventory helper 不可用，未完成可见浏览器回归。
  - 真实后端启动日志确认 `rerank_enabled=false`；上传专利法 TXT 后提问“发明专利权的保护期限是多少年？”返回“二十年”、第四十二条来源 10 条，SSE 思考文案为“证据按融合排序完成（精排已关闭）”。
  - `frontend/npm run build` 通过；本次改动涉及后端 SSE 文案，无需前端代码改动。
  - 当前本地 `.env` 已切换为 MiniLM 本地目录并开启 `RERANK_ENABLED=true`；旧 Qwen3 性能记录仅属于 Session 041 的历史验证，不再是当前启动配置。
  - README 本地相对链接 5 个均有效，2 个 Mermaid 代码块与全部 Markdown 围栏闭合；配置、API、仓库地址和功能边界已对照当前代码核验。
  - 最近一次真实 E2E 仍为 Session 034：GLM+Milvus 全断言通过，RAG 回答一句精准+【来源】一次通过；闲聊 curl 实测 0 regenerating。
- 验证后已清理：本轮创建的测试会话/新增专利法文档已删除，未触碰既有知识库数据；Milvus 三个容器保持运行状态；`backend/data/law_agent.db` 与搜索日志仍按 gitignore 留在本地。

## 本轮改动（Session 045：通过 Tavily Remote MCP 增加联网搜索）
- 文档先行同步 `docs/PRODUCT.md`、`docs/ARCHITECTURE.md`、`docs/RELIABILITY.md`，并同步 README、Mermaid 图、`feature_list.json`、`progress.md`。
- 后端新增 `WebSearchPort`、Tavily Remote MCP Streamable HTTP 适配器与 MCP v1 依赖（`mcp>=1.28,<2`）；新增 `TAVILY_API_KEY`、`TAVILY_MCP_URL`、搜索深度/条数配置、状态 API、`use_web_search` 请求参数、`web_sources`/`web_search_notice` SSE。
- 每次搜索在 `backend/log/web_search/` 独立生成完整 JSON `.log`，临时文件 + 原子替换、递归脱敏、永久保留；日志写入失败返回失败 tag，不将内存结果作为成功来源继续展示。
- 主图接线为 QueryRouter → Orchestrator → Web Search → observation → Orchestrator → Answer → Grounding → Final；按钮关闭时关键词只触发“请先开启按钮”提示，不调用 MCP；grounding 重试复用已获取结果。
- 前端新增持久在线模式按钮、配置 tag、网页来源折叠区、合法 URL、300 字预览和历史来源恢复；保留 Plugin Stub，删除旧 Web Search Stub。
- 验证：Docker/Milvus 可用时全量后端 **242 passed、1 warning**；前端 `npm run build` 通过；真实 Tavily SSE E2E 返回 5 条来源、日志和持久化断言通过；按钮关闭不触网；真实 RAG E2E 通过；浏览器可见回归因 CUA inventory helper 不可用未完成。
- 交接风险：部署环境需配置 `TAVILY_API_KEY`；本轮真实远程响应已验证，后续若 Tavily 返回结构变更应优先检查适配器的结构化/文本归一化日志。

## 本轮改动（Session 044：添加 MIT 开源协议）
- 新增根目录 `LICENSE`，采用标准 MIT License 文本，版权主体为 `law_agent contributors`。
- README 增加许可证说明和 `LICENSE` 链接。
- 本轮只涉及许可证与文档，不改运行时代码；上一轮全量测试结果为 226 passed、1 warning。

## 本轮改动（Session 043：删除低质量 fallback_generator_agent）
- 删除 `backend/app/agent/nodes/fallback_generator_agent.py`、`backend/app/agent/prompts/fallback_generator.py` 及主图注册、条件边、节点标签。
- grounding 未通过且 `max_global_steps` 耗尽时返回 `final`，由已有 `final_answer_node` 整理当前草稿；不再进行额外兜底 LLM 调用，think 事件说明预算收尾原因。
- Web/Plugin Stub 的未开通能力说明迁移到 `backend/app/agent/prompts/capability_notice.py`，保持原有能力边界提示，不与 fallback 语义混用。
- 文档与功能清单同步：ARCHITECTURE Mermaid、PRODUCT/RELIABILITY/README、`feature_list.json` BE-036/BE-047、`progress.md`。
- 验证：Milvus 重置后定向测试 22 passed、全量测试 226 passed、1 warning；后端启动日志与 `/api/health` 检查通过。SQLite 文件删除命令受执行环境破坏性操作策略拦截，未绕过该限制。

## 本轮改动（Session 042：统一 MiniLM Reranker 与本地下载启动）
- `Settings`、生产装配、`.env.example`、Reranker 默认值测试、ARCHITECTURE、PRODUCT 和 README 统一使用 `cross-encoder/ms-marco-MiniLM-L-6-v2`。
- `check_rerank_local.py` 改为幂等下载到 `.model/cross-encoder/ms-marco-MiniLM-L-6-v2`，校验 `config.json` 后加载本地 CrossEncoder，并输出模型、设备、分数和耗时。
- 本机忽略配置已改为新模型的本地目录并开启精排；`.model/` 已加入 `.gitignore`，模型权重不入库。
- 验证：Milvus 健康检查通过；模型脚本复用本地目录完成三条样本打分；后端全量测试 226 passed、1 warning；`git diff --check` 通过。

## 本轮改动（Session 041：修复精排状态误报）
- 根因：本地 `backend/.env` 显式设置 `RERANK_ENABLED=false`；模型并非坏掉。CPU 真实精排很慢，20 条候选实测超过 180s。
- 代码：`RerankResult` 增 `disabled`，`EvidenceRankingNode` 区分主动关闭/模型失败文案与 trace；关闭记 INFO、失败记 WARN；应用启动日志记录精排开关和设备。
- 文档/功能：同步 `docs/PRODUCT.md`、`docs/ARCHITECTURE.md`、`docs/RELIABILITY.md`、`feature_list.json`（BE-045）。
- 验证：定向 37 passed；全量 226 passed、1 warning；真实专利法问答正常返回“二十年”并带 10 条来源。

## 本轮改动（Session 040：GitHub 发布版 README）
- `README.md` 从极简启动说明扩展为完整项目首页：项目定位、技术亮点、系统/主图 Mermaid、RAG 与 SSE、技术栈、快速开始、配置/API、目录结构、测试、边界、贡献和 License 状态。
- Git 克隆地址使用当前 `origin`：`https://github.com/mark129873/law_agent_harness.git`；Docker 启动命令改为可从仓库根目录执行，补充 PowerShell 的 `curl.exe` 提示。
- 只陈述当前事实：SQLite 是唯一已启用数据库 Provider，Web Search/Plugin 仍为 Stub，MySQL 8.0 尚未接入，许可证文件尚未提供；未把二期规划写成现有能力。
- 验证：全量 pytest 225 passed、1 warning；前端 build 通过；README 本地链接与 Markdown 围栏检查通过；`feature_list.json` 无状态变化且冷热分层未触发。

## 本轮改动（Session 039：收紧失败路径重试预算）
- 用户要求仅减少 RAG 无对应文档的恢复次数与主图总体重试预算，不改变架构、节点或 LangGraph 连线。
- `backend/app/agent/subgraphs/legal_rag/config.py`：`max_retries` 从 2 调为 1，首次证据不足后最多恢复检索一轮。
- `backend/app/agent/config.py`：`max_global_steps` 从 4 调为 2，grounding 失败更快进入现有 fallback。
- 同步 `docs/ARCHITECTURE.md`、RAG 集成测试、主图预算单测和 `feature_list.json` 证据。
- 验证：相关测试 22 passed；全量 pytest 225 passed、1 warning；前端 build 通过；`git diff --check` 通过。
- 其他重试机制保持不变：Milvus 单查询异常重试 1 次、LLM 结构化输出解析重试 1 次。

## 本轮改动（Session 038：一期设计稿删除——30 条约束与 § 号速查并入 ARCHITECTURE §12）
- **普查先行**：代码引用 57 个设计 § 号 + 30 处"约束 N"——ARCHITECTURE.md 新增 §12：30 条强制约束逐条保编号收录 + 设计 §号速查表（核心内容 + 权威现落点）
- **删除**：docs/archive/legal_agent_phase1_technical_design.md（git rm）；ARCHITECTURE/agent/__init__ 引用改指 §12；设计 §XX/约束 N 语义自此由 §12 唯一承载
- **上一轮（Session 037，ba871d1）**：全文文档优化——Session 021~030 沉降、设计稿曾入冷存、去重复、补 README
- **上一轮（Session 036，f16a9ed）**：plan.md 悬空引用修复——硬约束清单迁 ARCHITECTURE §11、D1~D12 决策表迁 PRODUCT §6
- **上一轮（Session 033 Langfuse，0a14ca9/8f6e0fb）**：RELIABILITY/ARCHITECTURE + trace_sink 端口 + infrastructure sink + ChatService/包装器/LLMService 采集 + .env 开关
- **后端**：
  - `domain/services/trace_sink.py`：TraceSink/TraceSpan 协议 + trace_sink_var + current_trace_sink()
  - `agent/trace_context.py`：trace_span_var（当前节点 span，LLM generation 挂靠父 span）
  - `infrastructure/trace/langfuse_sink.py`：LangfuseTraceSpan/LangfuseTraceSink/LangfuseTraceSinkFactory（懒初始化、缺密钥 WARN 降级、全方法吞异常、`__call__ = create` 别名）+ null_trace_sink_factory
  - `agent/node_status.py`：包装器增 span 压栈/finally 弹栈（异常也 end，父级恢复）
  - `agent/services/llm_service.py`：invoke/structured_invoke（每次尝试一条）/stream（聚合增量）记 generation；messages 序列化 role 用 .value
  - `application/services/chat_service.py`：构造器增 trace_sink_factory；stream_answer 设/重置 ContextVar、start_trace/end_trace（正常 output/异常 error）、plan/sources/think/regenerating → record_event
  - `containers.py`：_build_trace_sink_factory 按 LANGFUSE_ENABLED 注入
  - `config/settings.py`：langfuse_enabled/base_url/public_key/secret_key
  - 测试：test_trace_sink.py（假客户端 6 例）、test_llm_service_trace.py（8 例）、test_chat_service_trace.py（4 例）、test_node_status 增 3 例、test_settings 增 2 例、DDD 守护加 langfuse
  - 用户 backend/.env：LANGFUSE_ENABLED=true（复用预置密钥与 LANGFUSE_BASE_URL）

## 仍损坏或未验证
- 已知缺陷：无
- 未验证路径：
  - Langfuse 自托管实例未验证（用户用云版；开关口径一致）
  - Ollama LLM 路径真实 E2E、MySQL 8.0
- 下一轮会话需要注意的风险：
  - **pymilvus load_dotenv 副作用升级**：.env 现含 LANGFUSE_ENABLED=true，会灌入测试进程环境——新增 API/集成测试时必须在 Settings 显式 `langfuse_enabled=False`（test_api 夹具已示范），否则测试触真实观测平台
  - **langfuse v4 查询口径**：验证/导出要用 `api.trace.get(id)` 完整详情或 observations.get_many 带 fields——get_many 裸调不返回 input/output/model，别误判为上报缺失
  - **SDK 后台批量上报**：网络受限时见 export timeout 日志（sink 吞异常不影响业务）；进程退出前如需强推可 `client.flush()`
  - **编排器"不 finish"误诊已修正（BE-044）**：旧记录"judge 对 direct 路径过度敏感"实为编排器重复选 direct_answer（Langfuse 时间线取证）——若回归先查编排决策的 generation 留档（api.trace.get），不要想当然调 judge Prompt
  - **Prompt 修改纪律**：9 个角色标记词（意图路由器/顶层编排器/回答校验器/检索规划器/改写器/子查询生成器/扩展器/证据评估器/恢复规划器）与 BE-017 字面锚点被测试断言，改 Prompt 前先查 tests 的 marker/锚点清单（docs/ARCHITECTURE.md §11「Prompt 与事件硬约束契约」有全列表）
  - 既有风险不变：每问题 LLM 调用 5~8 次；BE-017 字面锚点三方联动
  - **ADR 体系已删除（Session 035）**：注释/文档不得再新增 ADR-XXXX 引用；架构决策统一引用 docs/ARCHITECTURE.md
  - **Windows 端口清理**：停 uvicorn/npm 后子进程可能残留占端口，需 netstat 找 PID + taskkill //F
 - 下一步最佳动作（需用户决定）：继续失败查询链路优化（已量化：最坏 20 次 LLM/24 检索/3 重排；方案=恢复轮经济模式+零新增早退+同能力防重入护栏+预算参数可配）；可选产品增强（会话重命名/停止按钮/CORS 收敛）；MySQL 8.0 接入
- 这一步中哪些东西不要动：后端 API 契约（§7 SSE）；领域层零技术依赖（langfuse 已入守护名单，只允许 infrastructure/trace）；**trace_sink_var 的注入时机（必须在图任务创建前 set）**；**LangfuseTraceSink 全方法吞异常原则**；双预算常量；BE-017 字面锚点联动

## 命令
- Milvus 启动：`cd backend && docker start milvus-etcd milvus-minio milvus-standalone`
- 后端启动：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 干净环境重置（两步）：删除 `backend/data/` + `uv run python scripts/reset_milvus.py`
- 后端验证：`cd backend && uv run pytest tests -q -rs`（全量 242 项；Docker/Milvus 可用时本轮 242 passed、1 warning）
- 前端构建/启动：`cd frontend && npm run build` / `npm run dev`
- 端到端：启动服务器后 `PYTHONPATH=backend uv run --with httpx python backend/scripts/verify_real_e2e.py`；联网搜索真实 SSE E2E 使用 `use_web_search=true`，结果保留在 `backend/log/web_search/`
- Langfuse 云端查证：`api.trace.list / api.trace.get(id)`（完整详情含 observations IO）
- 图导出：`cd backend && uv run python scripts/export_qa_graph.py`

