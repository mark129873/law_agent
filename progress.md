# progress.md -- 会话进度日志

## 当前已验证状态
- 当前工作树：`C:\Users\nnnnnn\.codex\worktrees\43a6\law_agent`（detached HEAD）；已有 Session 052 未提交修改予以保留。
- 标准启动路径：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`（`MILVUS_PROVIDER` 默认 `cloud` 读取 `MILVUS_CLOUD_*`；本地 standalone 必须显式设为 `local` 并启动 Docker）
- 标准验证路径：`cd backend && uv run pytest tests -q -rs`；本轮使用已有虚拟环境的 Python 执行同一测试集，256 passed、5 skipped（Milvus 不可达）、1 warning；服务配置齐全后启动并检查 `/api/health`。
- Agent 模块一期重写（BE-032~041 + FE-014/015 + BE-040）+ 思考块增强（BE-042 + FE-016）+ Langfuse trace（BE-043）+ 全量 Prompt 优化（BE-044）+ 精排状态语义修复（BE-045）+ Reranker 模型统一（BE-046）+ 低质量兜底 Agent 删除（BE-047）+ Tavily Remote MCP 搜索（BE-048/FE-017）全部 passing：主图 + Local Legal RAG 子图 + Tavily Web Search + Plugin Stub + 服务层 + 豆包式思考块 + Langfuse 全链路追踪（.env 开关）+ 12 个 Prompt 五段结构化；grounding 预算耗尽直接确定性收尾，架构决策见 docs/ARCHITECTURE.md
- 当前 Reranker：全项目统一使用 `cross-encoder/ms-marco-MiniLM-L-6-v2`；`check_rerank_local.py` 首次下载到根目录 `.model/cross-encoder/ms-marco-MiniLM-L-6-v2` 并执行 CPU 样本打分。本地 `.env` 已切换为该模型并开启 `RERANK_ENABLED=true`；无法使用时仍按既有故障降级契约记录 WARN。
- 当前失败路径预算：`AgentConfig.max_global_steps=2`、`LegalRAGConfig.max_retries=1`；grounding 未通过且预算耗尽时直接进入 `final_answer_node`，不再调用额外兜底 LLM；其他重试机制不变
- 当前最高优先级未完成功能：BE-049 已保留 prepare/workflow 生成质量评测、数据集和旧版隔离配置历史基线；仍需在共享知识库配置下重跑真实模型评测，不能将旧基线写成当前配置已验证。
- 当前 blocker：此 worktree 尚无 `.env` 和 Milvus Cloud 连接配置；旧版真实 workflow 23 条中 13 条出现 GLM `ConnectError`/HTTP 400，模型稳定性问题待验证。前端未改动。
- 法律条文边界优先 Chunk 切分（BE-052）已 passing：识别行首法条标题，短法条可合并，超长法条保持原子性；普通文本仍使用原有段落与滑窗规则。
- 冷数据归档：docs/archive/progress-archive-001-010.md、progress-archive-011-020.md、progress-archive-021-030.md、progress-archive-031-040.md（Session 001~040 历史记录；沉降规则：Session > 15 触发，每批沉 10 个，起止序号命名）

### Session 053（评测收敛为 RAG 生成质量）（2026-09-19）
- 按用户确认删除 api-smoke 子命令、实现、专用测试和报告渲染；文档导入迁移到 `app/evaluation/corpus.py`，保留 prepare/workflow。
- README 改为「RAG 评测」，说明 Judge 四维评分、门槛、辅助指标和报告；同步架构、产品、可靠性与功能清单，历史基线仅展示 RAG 质量结果。
- 测试前确认当前 worktree 无 SQLite/WAL/SHM、无后端进程且未配置 Milvus；复用已有 Python 环境执行离线回归，不启动 Docker、不操作其他工作树知识库。
- 验证：全量 pytest 256 passed、5 skipped、1 warning（含现有 API 集成测试）；CLI 三种 help、compileall、JSON 与 diff 检查通过。13 个热层 Session、23 个 passing 热条目、40 个归档条目，共 68 个功能，无需沉降。
- 本轮开始前已有 13 个文件未提交，其中与当前修改存在重叠；保留原改动，不将其代为提交。真实服务启动和模型质量分数未在本轮重测。

### Session 050（Milvus 显式部署选择与 DeepSeek）（2026-09-18）
- 新增 `MILVUS_PROVIDER=cloud|local`，默认 cloud；cloud 使用 `MILVUS_CLOUD_URI/TOKEN`，local 使用 `MILVUS_URI/TOKEN`，不再按 URI 是否存在自动回退。
- 新增 DeepSeek OpenAI 兼容 Provider，可用于主 LLM、Planner 和 Judge；固定发送 `thinking.type=disabled`，API Key 只从环境注入。
- 验证：定向 29 passed；全量 `uv run pytest tests -q -rs` 为 255 passed、5 skipped、1 warning；当前 `.env` 云端 Milvus 初始化成功，DeepSeek `deepseek-chat` 实际返回非空答案；compileall、git diff --check 通过。

### Session 051（明确测试环境清理步骤）（2026-09-19）
- 更新 `docs/RELIABILITY.md`：明确下次 Codex 测试前先删除当前 `SQLITE_DB_PATH` 对应的 SQLite 测试数据库及 WAL/SHM 文件，再执行 `uv run python scripts/reset_milvus.py --yes` 删除当前配置的 Milvus 测试集合。
- 本轮仅更新测试运维文档，不改业务代码；已执行 diff 校验与 JSON 校验。

### Session 052（评测复用业务存储）（2026-09-19）
- RAG 评测改为复用当前 `MILVUS_COLLECTION_NAME` 和 `SQLITE_DB_PATH`，删除 `law_agent_eval*` 集合强制校验及评测专用启动配置。
- `prepare` 默认只追加测试文档；全量清理改为显式 `prepare --reset`，并在 README、PRODUCT、ARCHITECTURE、RELIABILITY 和 `.env.example` 标注其破坏性。
- 历史真实结果保留在 `docs/evaluation-baseline.md`，明确它来自旧版隔离配置，不冒充当前共享知识库基线。

### Session 049（Milvus Cloud 默认连接）（2026-09-18）
- Settings 优先读取 `MILVUS_CLOUD_URI` / `MILVUS_CLOUD_TOKEN`，并把 API Key 传入 `MilvusVectorStore`；旧 `MILVUS_URI` / `MILVUS_TOKEN` 保留给 standalone 回退。
- 更新 README、`.env.example`、ARCHITECTURE、PRODUCT、RELIABILITY 和 init；认证重置脚本要求 `--yes`，避免默认云端配置误删集合。
- 验证：真实项目装配连接 Zilliz Cloud 成功（authenticated=true）；应用启动完成，`/api/health` 返回 200；定向 14 passed；全量 250 passed、5 skipped、1 warning；compileall、JSON、git diff --check 通过。

### Session 048（测试数据同步与真实 RAG 基线）（2026-09-18）
- 用户删除了 `中华人民共和国专利法（要点笔记）.md` 和 `民事诉讼法2021.md`；已删除评测数据集中对应的民事诉讼案例，真实 E2E 脚本不再上传已删 Markdown，pytest 数据集测试改为 23 条并校验来源文件存在。
- 当前导入 5 份测试文档到 `law_agent_eval`；真实 workflow 报告 `20260918T132908Z-cabbe758`：23 条中 10 条完成、13 条 GLM `ConnectError`/HTTP 400，完成样本 Hit@5 90%、MRR 0.8333；API/SSE 冒烟报告 `api-smoke-20260918T133249Z-0ddb95` 2/2 通过。
- Milvus 恢复后全量 `uv run pytest tests -q -rs` 为 254 passed、1 warning；评测基线摘要已写入 `docs/evaluation-baseline.md`。BE-049 保持 `in_progress`，未把外部模型失败伪装为 passing。

### Session 047（跳过 Milvus 的离线收尾）（2026-09-18）
- 本轮动作：按用户要求关闭 Docker Desktop，跳过 Milvus 真实运行；不生成虚构的 RAG 基线分数。
- 验证：评测单测 12 passed；全量 `uv run pytest tests -q -rs` 为 249 passed、5 skipped（5 个 Milvus 集成用例因服务不可达跳过）、1 warning；`compileall`、CLI help、`npm run build`、`git diff --check` 通过。
- 当前结论：BE-049 的代码和离线验证完成，真实向量检索/LLM/Judge 报告仍待 Docker/Milvus 恢复后执行；Docker 进程已关闭。

### Session 046（RAG 评测演示文档与双入口运行器）
- 日期：2026-09-18
- 本轮目标：实现 RAG 端到端评测演示文档配套的真实工作流评测、HTTP/SSE 冒烟、可配置 Judge、指标和 JSON/Markdown 报告。
- 改动：新增 23 条法律 JSONL 数据集（与当前保留的 5 份测试文本同步）；容器统一注册 `QaWorkflow`；新增 Recall/Hit@K、MRR、引用精确率/召回率、状态/grounding、节点耗时和 LLM Judge；新增独立 Milvus 集合与 Judge 配置；新增 `scripts/evaluate_rag.py` 的 `prepare`、`workflow`、`api-smoke` 三个入口；报告写入 gitignore 的 `backend/log/evaluation/`。
- 文档：同步 ARCHITECTURE、PRODUCT、RELIABILITY、README 和 `.env.example`；定位统一为 RAG 评测演示文档，不新增前端页面。
- 验证：新增评测单测 12 passed；首次全量测试为 246 passed、5 skipped（Milvus 不可达）、1 warning；设置隔离集合后真实 workflow 尝试在 Milvus 初始化阶段因 `127.0.0.1:19530` 不可达失败，未生成虚构基线分数。后续离线收尾结果见 Session 047。
- 风险/交接：需要启动 Milvus、Embedding/LLM、Reranker 后，按 README 的独立集合和 SQLite 配置执行 prepare → workflow → api-smoke；真实运行后再提交脱敏汇总基线，并把 BE-049 标为 passing。

### Session 045（通过 Tavily Remote MCP 增加联网搜索）
- 日期：2026-09-16
- 本轮目标：用户通过「联网搜索」按钮触发 Tavily Remote MCP；搜索结果进入 observation→回答生成→grounding→最终收尾，并为每次搜索独立永久留档。
- 改动：文档先行同步 PRODUCT/ARCHITECTURE/RELIABILITY；新增 `WebSearchPort`、Tavily Streamable HTTP 适配器、MCP v1 依赖与配置、原始/规范化结果原子 JSON 日志；新增 `use_web_search` 与状态 API、`web_sources`/`web_search_notice` SSE；前端新增持久在线模式按钮、配置 tag、联网来源折叠区、合法 URL 与 300 字预览；移除 Web Search Stub，保留 Plugin Stub；补齐单测、主图和 API 集成测试。
- 验证：Docker/Milvus 可用时 `cd backend && uv run pytest tests -q -rs` → 242 passed、1 warning（5 个 Milvus 用例均实际执行）；真实 Tavily SSE E2E 返回 5 条网页来源，完成 `web_sources→delta→done`、来源持久化和独立日志断言；按钮关闭时未触网；`scripts/verify_real_e2e.py` 真实 Milvus/GLM RAG E2E 通过；`cd frontend && npm run build`、`git diff --check`、JSON 校验通过。CUA inventory helper 不可用，未完成可见浏览器实操。
- 风险/交接：部署环境仍需配置 `TAVILY_API_KEY`；搜索日志写入 `backend/log/web_search/` 后永久保留且已 gitignore，本轮产生的 1 个真实搜索日志已保留且未进入 Git；无真实联网链路 blocker。

### Session 054（法律条文边界优先 Chunk 切分）
- 日期：2026-09-19
- 本轮目标：优化法律文档上传切分，避免法条被从中间截断。
- 改动：`chunk_text` 识别行首“第 X 条”法条标题；短法条按目标长度合并，超长法条作为完整原子 chunk；普通文本保持原段落滑窗；同步 ARCHITECTURE、PRODUCT 与 BE-052。
- 验证：Milvus 健康、后端 `/api/health`、20 个切分/入库定向测试、真实专利法第四十二条完整性探针、全量 pytest **227 passed、1 warning**；`git diff --check` 通过。
- 风险：未识别到明确法条标题的扫描件或普通文本仍使用原滑窗规则。

### Session 044（添加 MIT 开源协议）
- 日期：2026-09-14
- 本轮目标：为仓库添加标准 MIT 开源协议并在 README 中声明。
- 改动：新增根目录 `LICENSE`，版权主体标注为 `law_agent contributors`；README 增加 MIT License 链接。
- 验证：许可证文件、README 链接和工作区状态检查通过；本轮未修改运行时代码，沿用上一轮全量 pytest 226 passed、1 warning。

### Session 043（删除低质量 fallback_generator_agent）
- 日期：2026-09-14
- 本轮目标：删除实际效果不佳的 `fallback_generator_agent`，避免 grounding 预算耗尽后再次调用 LLM 覆盖已有回答。
- 改动：删除 `FallbackGeneratorAgent`、独立 fallback Prompt、主图节点、节点标签及 fallback 条件边；预算耗尽直接进入确定性 `final_answer_node`；Web/Plugin 未开通说明迁移到 `capability_notice.py`。
- 验证：Milvus 集合重置后，代码变更后的定向测试 22 passed、全量 pytest 226 passed、1 warning；后端启动与健康检查通过，路由和 Mermaid 图同步完成。SQLite 文件删除命令受执行环境破坏性操作策略拦截，未绕过该限制。
- 风险/交接：预算耗尽时不再自动重写，收尾使用 `answer_generator_agent` 已生成的最后草稿；若需改善答案质量，应优化主回答/grounding Prompt 或预算策略，而不是恢复低质量兜底 Agent。

### Session 042（统一 MiniLM Reranker 与本地下载启动）
- 日期：2026-09-14
- 本轮目标：将全项目 Reranker 切换为 `check_rerank_local.py` 中的 `cross-encoder/ms-marco-MiniLM-L-6-v2`，并补齐模型下载、配置和启动说明。
- 改动：Settings、装配点、`.env.example`、测试默认值、架构/产品文档和 README 全部同步；检查脚本统一负责下载到 `.model`、本地加载和样本打分；本机忽略配置切换到新模型并开启精排；新增 BE-046。
- 验证：Milvus 健康检查通过；模型检查脚本复用本地目录并完成打分；后端全量测试 226 passed、1 warning；`git diff --check` 通过。
- 风险/交接：首次下载需要访问 Hugging Face；CPU/GPU 设备由 `RERANKER_DEVICE` 配置，模型加载或推理异常仍会按既有契约降级为 RRF。

### Session 041（修复精排状态误报）
- 日期：2026-09-14
- 本轮目标：排查“证据重排降级（精排不可用）”是否由 reranker 故障导致，并修复主动关闭精排时的误导性思考文案。
- 根因与决策：工作区 `.env` 曾显式设置 `RERANK_ENABLED=false`，不是模型加载失败；本地 Qwen3-Reranker 快照实测可加载并返回分数，但 CPU 对 20 条候选超过 180s，因此恢复安全的 CPU 默认关闭，不把它改成会卡死请求的强制开启。
- 改动：`RerankResult` 增 `disabled` 状态；EvidenceRankingNode 区分“精排已关闭”和“模型失败降级”；主动关闭记 INFO，模型失败仍记 WARN；启动日志增加 `rerank_enabled`/`reranker_device`；同步 PRODUCT/ARCHITECTURE/RELIABILITY 与 BE-045。
- 验证：Milvus 集合重置；相关单测 37 passed；全量 `uv run pytest tests -q -rs` 为 **226 passed, 1 warning**；`frontend/npm run build` 通过；真实启动日志确认 `rerank_enabled=false`；上传专利法后提问“发明专利权的保护期限是多少年？”返回“二十年”、第四十二条来源 10 条，SSE 思考显示“证据按融合排序完成（精排已关闭）”。
- 风险/交接：若要真实精排，请在 GPU 或可接受长延迟的机器设置 `RERANK_ENABLED=true`；当前 CPU 配置无需再把“精排已关闭”误判为项目故障。

