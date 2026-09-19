# progress.md -- 会话进度日志

## 当前已验证状态
- 当前主工作树：`C:\Users\nnnnnn\Desktop\law_agent`（`feature/auto_coder`，核心代码提交 `79f6f8a`，全项目审计改动待提交）；`codex/archive-cleanup` 隔离 worktree 保留在历史提交 `73255d6`，未合并分支为空。
- 标准启动路径：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`（`MILVUS_PROVIDER` 默认 `cloud` 读取 `MILVUS_CLOUD_*`；本地 standalone 必须显式设为 `local` 并启动 Docker）
- 标准验证路径：`cd backend && uv run pytest tests -q -rs`；本轮 259 passed、5 skipped（Milvus 集成服务不可达）、1 warning；服务配置齐全后启动并检查 `/api/health`。
- Agent 模块一期重写（BE-032~041 + FE-014/015 + BE-040）+ 思考块增强（BE-042 + FE-016）+ Langfuse trace（BE-043）+ 全量 Prompt 优化（BE-044）+ 精排状态语义修复（BE-045）+ Reranker 模型统一（BE-046）+ 低质量兜底 Agent 删除（BE-047）+ Tavily Remote MCP 搜索（BE-048/FE-017）全部 passing：主图 + Local Legal RAG 子图 + Tavily Web Search + Plugin Stub + 服务层 + 豆包式思考块 + Langfuse 全链路追踪（.env 开关）+ 12 个 Prompt 五段结构化；grounding 预算耗尽直接确定性收尾，架构决策见 docs/ARCHITECTURE.md
- 当前 Reranker：全项目统一使用 `cross-encoder/ms-marco-MiniLM-L-6-v2`；`check_rerank_local.py` 首次下载到根目录 `.model/cross-encoder/ms-marco-MiniLM-L-6-v2` 并执行 CPU 样本打分。本地 `.env` 已切换为该模型并开启 `RERANK_ENABLED=true`；无法使用时仍按既有故障降级契约记录 WARN。
- 当前失败路径预算：`AgentConfig.max_global_steps=2`、`LegalRAGConfig.max_retries=1`；grounding 未通过且预算耗尽时直接进入 `final_answer_node`，不再调用额外兜底 LLM；其他重试机制不变
- 当前最高优先级未完成功能：BE-049 已完成一次共享知识库真实模型评测，但质量未达门槛；报告保留在 `backend/log/evaluation/20260919T053533Z-7f6b9aab/`，不能将本次结果写成 passing。
- 当前 blocker：本轮基于 Langfuse 失败 trace 完成查询恢复、路由、回答和 Judge 优化，但重新 `prepare --reset` 时本机没有 Ollama embedding 服务（11434 无监听），因此没有新的真实质量分数；BE-049 继续 `in_progress`，前端未改动。

### Session 060（Langfuse 驱动的 RAG 提示词与评测门控优化）（2026-09-19）
- 根因：Langfuse LF-002 等 trace 显示恢复查询丢失专利法条号等精确锚点；`互联网` 被误判为联网意图；Judge 未把期望/实际状态纳入通过门槛，且对产品允许的来源文件引用过严。
- 最小改动：恢复规划器把法条号、期限、主体和条件传入下一轮查询变体；混合召回由 20 扩至 30、精排候选上限为 32；路由增加显式联网意图守卫；证据 Grader 改为问题范围判断；回答按子问题逐项作答；Judge 对状态与 `【来源：文件名】` 协议统一评分；同步 EI-001 评测契约。主图和 RAG 子图拓扑未变，Langfuse 默认开启。
- 验证：全量 `uv run pytest tests -q -rs` 为 259 passed、5 skipped、1 warning；compileall、JSON、`git diff --check` 通过；标准 `uv run uvicorn` 启动成功，`GET /api/health` 返回 200。
- 真实复评：`prepare --reset` 在首份文档 embedding 阶段因本机无 Ollama 服务失败，已删除本次产生的失败元数据记录，未改写已有真实评测指标；下一轮需恢复 Ollama 后再验证质量变化。
- 法律条文边界优先 Chunk 切分（BE-052）已 passing：识别行首法条标题，短法条可合并，超长法条保持原子性；普通文本仍使用原有段落与滑窗规则。
- 冷数据归档：docs/archive/progress-archive-001-010.md、progress-archive-011-020.md、progress-archive-021-030.md、progress-archive-031-040.md（Session 001~040 历史记录；沉降规则：Session > 15 触发，每批沉 10 个，起止序号命名）

### Session 061（全项目代码与文档一致性审计）（2026-09-19）
- 修正架构文档的 RRF 预截断值（20→32）和测试统计（单元 186、集成 66、接口 12、自动化合计 264；本轮 259 passed/5 skipped/1 warning）；修正功能清单的 `LANGFUSE_BASE_URL` 字段名，并把交接文档旧快照明确标为历史。
- 修正三个真实验证脚本的硬编码用户目录，改为按 `__file__` 定位 backend；README 克隆地址与当前 remote 同步为 `mark129873/law_agent.git`。
- 验证：后端全量 pytest 259 passed、5 skipped、1 warning；前端 `npm run build` 通过；compileall、LangGraph 图导出、评测 CLI help、JSON 与 `git diff --check` 通过；Settings 与 `.env.example` 均覆盖 40 个配置字段，活动代码无旧 Planner Provider 引用。

### Session 059（直调 RAG 评测接入 Langfuse）（2026-09-19）
- 根因确认：`workflow` 评测直接调用 `QaWorkflow.ainvoke()`，原先绕过 `ChatService`，因此真实评测报告没有 Langfuse trace，只有工作流内置节点摘要。
- 最小改动：评测运行器按案例建立 `evaluation-<case_id>` trace，把节点 span、LLM generation、流程事件和 `evaluation_judge` span 接入同一条链路；`EvaluationCaseResult` 保存 `trace_id`；Langfuse v4 使用一等 `session_id`，评测结束显式 shutdown 等待批量上报。
- 真实验证：第二轮共享配置评测 23/23 完成、0 条 workflow failure、23/23 唯一 trace 可查询；Hit@5/Recall@5=0.913、MRR=0.8406、grounding=0.8696、Judge 通过率=0.5217、平均延迟 11.24s。报告：`backend/log/evaluation/20260919T053533Z-7f6b9aab/`。
- Langfuse 取证：LF-002 首轮及恢复轮均显示缺少专利法第三十五至三十八条证据，导致状态不足和 Judge 完整性扣分；本轮未擅自修改检索算法、数据集预期或质量门槛。
- 验证：trace/评测定向 16 passed；全量 `uv run pytest tests -q -rs` 为 258 passed、5 skipped、1 warning；compileall、JSON 与 `git diff --check` 通过；评测后已清理 SQLite 和 Milvus `law_chunks`。commit `a004376`。

### Session 058（真实共享 RAG 评测与 clean-state 收尾）（2026-09-19）
- 使用当前本地配置启动后端：主 LLM 为 DeepSeek、Judge `follow` 复用主 LLM，Embedding 为 Ollama，Milvus Cloud 使用 `law_chunks`，启用 MiniLM Reranker。
- `prepare` 导入 5 份测试文档；`workflow` 运行 23 条案例，23/23 完成、0 条 workflow failure。结果：Hit@5/Recall@5=0.913、MRR=0.8623、grounding 通过率=0.8261、Judge 通过率=0.5217、平均延迟 11.0s；质量尚未达到 passing。
- 报告：`backend/log/evaluation/20260919T051128Z-514ba54b/`；真实 Judge 使用 `deepseek-v4-flash`。评测后按 RELIABILITY 清理 SQLite（含临时评测库）和 Milvus `law_chunks`，保留报告工件。
- 结论：BE-049 继续保持 `in_progress`。11 条状态预期不匹配、4 条 grounding 失败和 11 条 Judge 未通过案例需要后续区分数据集契约问题与检索/回答质量问题，未在本轮擅自改数据集或放宽门槛。

### Session 057（规划器与评测 Judge 配置收敛）（2026-09-19）
- 规划器删除独立 Provider/模型配置，工作流构建器、RAG 子图和主图节点统一复用同一个主 LLM 实例；`PlannerProvider` 改为仅历史记录，代码配置移除。
- RAG 评测新增并使用 `JudgeProvider`，保留 `follow` 默认复用主 LLM、显式 Provider/模型时构造独立 Judge；主 LLM 默认值同步为 DeepSeek。
- 同步 `Settings`、容器装配、README、`.env.example`、ARCHITECTURE、PRODUCT 与配置测试；本地 `.env` 删除已废弃的 `PLANNER_*` 字段。
- 验证：定向 25 passed；全量 `uv run pytest tests -q -rs` 为 257 passed、5 skipped、1 warning；compileall、图导出、JSON、`git diff --check` 和后端 `/api/health` 200 通过；commit `6934409`。
- 风险：BE-049 仍为 `in_progress`，真实共享 Milvus/Embedding/LLM/Reranker/Judge 质量评测尚未重跑。

### Session 055（archive-cleanup 合并收尾）（2026-09-19）
- 从 `refs/codex/snapshots/bd9e467f0a2c692deaa8ed62908fd148d6ea2e54` 恢复 `codex/archive-cleanup`，与后续评测重构整合；保留 `corpus.py` 与 `prepare/workflow` 入口，不恢复已删除的 `api-smoke/http_smoke`。
- 当前工作区 DeepSeek V4 Flash 配置已由 `898393a` 提交；archive-cleanup 合并提交 `c92e777` 已快进合入 `feature/auto_coder`。
- 验证：全量 pytest 257 passed、5 skipped、1 warning；CLI help、compileall、JSON、冲突标记和 diff 检查通过。
- BE-049 仍为 `in_progress`；真实共享 Milvus/LLM/Judge 质量评测尚未重跑，旧版基线不作为当前配置结论。

### Session 056（环境配置字段同步）（2026-09-19）
- 按当前 `Settings` 同步本地 `backend/.env` 与 `backend/.env.example`：补齐服务、日志、数据库、Milvus、Planner/Judge、Reranker、Langfuse 和 Tavily 字段；保留本地密钥，不提交 `.env`。
- 将 DeepSeek 默认模型、Tavily 搜索深度和 Reranker 示例路径说明同步到当前实现；README 与 ARCHITECTURE 的 DeepSeek 默认模型改为 `deepseek-v4-flash`。
- 验证：42 个配置字段完整覆盖 `.env`/`.env.example`；Settings 实际解析通过；配置与评测相关测试 27 passed，`git diff --check` 通过。

### Session 053（评测收敛为 RAG 生成质量）（2026-09-19）
- 按用户确认删除 api-smoke 子命令、实现、专用测试和报告渲染；文档导入迁移到 `app/evaluation/corpus.py`，保留 prepare/workflow。
- README 改为「RAG 评测」，说明 Judge 四维评分、门槛、辅助指标和报告；同步架构、产品、可靠性与功能清单，历史基线仅展示 RAG 质量结果。
- 测试前确认当前 worktree 无 SQLite/WAL/SHM、无后端进程且未配置 Milvus；复用已有 Python 环境执行离线回归，不启动 Docker、不操作其他工作树知识库。
- 验证：全量 pytest 256 passed、5 skipped、1 warning（含现有 API 集成测试）；CLI 三种 help、compileall、JSON 与 diff 检查通过。13 个热层 Session、23 个 passing 热条目、40 个归档条目，共 68 个功能，无需沉降。
- 本轮开始前已有 13 个文件未提交，其中与当前修改存在重叠；保留原改动，不将其代为提交。真实服务启动和模型质量分数未在本轮重测。

### Session 051（明确测试环境清理步骤）（2026-09-19）
- 更新 `docs/RELIABILITY.md`：明确下次 Codex 测试前先删除当前 `SQLITE_DB_PATH` 对应的 SQLite 测试数据库及 WAL/SHM 文件，再执行 `uv run python scripts/reset_milvus.py --yes` 删除当前配置的 Milvus 测试集合。
- 本轮仅更新测试运维文档，不改业务代码；已执行 diff 校验与 JSON 校验。

### Session 052（评测复用业务存储）（2026-09-19）
- RAG 评测改为复用当前 `MILVUS_COLLECTION_NAME` 和 `SQLITE_DB_PATH`，删除 `law_agent_eval*` 集合强制校验及评测专用启动配置。
- `prepare` 默认只追加测试文档；全量清理改为显式 `prepare --reset`，并在 README、PRODUCT、ARCHITECTURE、RELIABILITY 和 `.env.example` 标注其破坏性。
- 历史真实结果保留在 `docs/evaluation-baseline.md`，明确它来自旧版隔离配置，不冒充当前共享知识库基线。

### Session 054（法律条文边界优先 Chunk 切分）
- 日期：2026-09-19
- 本轮目标：优化法律文档上传切分，避免法条被从中间截断。
- 改动：`chunk_text` 识别行首“第 X 条”法条标题；短法条按目标长度合并，超长法条作为完整原子 chunk；普通文本保持原段落滑窗；同步 ARCHITECTURE、PRODUCT 与 BE-052。
- 验证：Milvus 健康、后端 `/api/health`、20 个切分/入库定向测试、真实专利法第四十二条完整性探针、全量 pytest **227 passed、1 warning**；`git diff --check` 通过。
- 风险：未识别到明确法条标题的扫描件或普通文本仍使用原滑窗规则。

