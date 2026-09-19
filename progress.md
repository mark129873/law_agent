# progress.md -- 会话进度日志

## 当前已验证状态
- 当前主工作树：`C:\Users\nnnnnn\Desktop\law_agent`（`feature/auto_coder`，HEAD `6934409`）；`codex/archive-cleanup` 隔离 worktree 已同步到同一提交，未合并分支为空。
- 标准启动路径：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`（`MILVUS_PROVIDER` 默认 `cloud` 读取 `MILVUS_CLOUD_*`；本地 standalone 必须显式设为 `local` 并启动 Docker）
- 标准验证路径：`cd backend && uv run pytest tests -q -rs`；本轮 257 passed、5 skipped（Milvus 不可达）、1 warning；服务配置齐全后启动并检查 `/api/health`。
- Agent 模块一期重写（BE-032~041 + FE-014/015 + BE-040）+ 思考块增强（BE-042 + FE-016）+ Langfuse trace（BE-043）+ 全量 Prompt 优化（BE-044）+ 精排状态语义修复（BE-045）+ Reranker 模型统一（BE-046）+ 低质量兜底 Agent 删除（BE-047）+ Tavily Remote MCP 搜索（BE-048/FE-017）全部 passing：主图 + Local Legal RAG 子图 + Tavily Web Search + Plugin Stub + 服务层 + 豆包式思考块 + Langfuse 全链路追踪（.env 开关）+ 12 个 Prompt 五段结构化；grounding 预算耗尽直接确定性收尾，架构决策见 docs/ARCHITECTURE.md
- 当前 Reranker：全项目统一使用 `cross-encoder/ms-marco-MiniLM-L-6-v2`；`check_rerank_local.py` 首次下载到根目录 `.model/cross-encoder/ms-marco-MiniLM-L-6-v2` 并执行 CPU 样本打分。本地 `.env` 已切换为该模型并开启 `RERANK_ENABLED=true`；无法使用时仍按既有故障降级契约记录 WARN。
- 当前失败路径预算：`AgentConfig.max_global_steps=2`、`LegalRAGConfig.max_retries=1`；grounding 未通过且预算耗尽时直接进入 `final_answer_node`，不再调用额外兜底 LLM；其他重试机制不变
- 当前最高优先级未完成功能：BE-049 已保留 prepare/workflow 生成质量评测、数据集和旧版隔离配置历史基线；仍需在共享知识库配置下重跑真实模型评测，不能将旧基线写成当前配置已验证。
- 当前 blocker：此 worktree 尚无 `.env` 和 Milvus Cloud 连接配置；旧版真实 workflow 23 条中 13 条出现 GLM `ConnectError`/HTTP 400，模型稳定性问题待验证。前端未改动。
- 法律条文边界优先 Chunk 切分（BE-052）已 passing：识别行首法条标题，短法条可合并，超长法条保持原子性；普通文本仍使用原有段落与滑窗规则。
- 冷数据归档：docs/archive/progress-archive-001-010.md、progress-archive-011-020.md、progress-archive-021-030.md、progress-archive-031-040.md（Session 001~040 历史记录；沉降规则：Session > 15 触发，每批沉 10 个，起止序号命名）

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

