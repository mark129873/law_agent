# progress.md -- 会话进度日志

## 当前已验证状态
- 仓库根目录：`C:\Users\nnnnnn\Desktop\law_agent`
- 标准启动路径：`cd backend && uv sync && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 标准验证路径：`cd backend && uv run pytest tests -q`；启动后 `curl http://127.0.0.1:8000/api/health`
- 当前最高优先级未完成功能：BE-006 向量数据库抽象层
- 当前 blocker：无

### Session 003
- 日期：2026-09-06
- 本轮目标：BE-003 / BE-004 / BE-005（用户指定"完成 3 个 feature"）
- 技术决策：
  - BE-003：自研轻量 DIContainer（接口注册工厂+单例），不引入 DI 框架；containers.py 为唯一装配点，挂载到 app.state.container。
  - BE-004：领域实体用纯 dataclass（零技术依赖）；Repository 接口在 domain 层；Database 抽象含 transaction() 事务上下文。
  - BE-005：aiosqlite 实现；提交边界由 Database 层统一控制（_tx_depth 计数），仓库不自行 commit——测试暴露了"仓库自动提交破坏外层事务回滚"的真实缺陷后修正。
  - 本机环境备注：Ollama 已运行（模型 qwen3.5:9b，非默认配置的 qwen2.5:7b，BE-010 时需对齐）；GLM_API_KEY 未设置。
- 已完成：DI 容器与装配点、领域实体与 Repository 接口、Database 抽象、SQLite 实现、lifespan 自动建库
- 运行过的验证：
  - `uv run pytest tests -q` → 18 passed（DI 4 + 数据库抽象 4 + SQLite 6 + 健康检查 1 + 配置 4，共 18；其中 SQLite 含持久化/级联/事务回滚/幂等）
  - 真实启动：删除 data/law_agent.db 后启动自动建库，日志 "Database initialized"，curl /api/health → ok
- 已记录证据：feature_list.json BE-003/BE-004/BE-005 evidence
- 提交记录：1b0b9a8 (BE-003)、942b4d6 (BE-004)、本轮 BE-005 提交
- 更新过的文件或工件：docs/ARCHITECTURE.md（第 15-17 节）、app/common/di.py、app/containers.py、app/main.py、domain/entities/**、domain/repositories/**、infrastructure/database/**、tests/**、pyproject.toml（aiosqlite）、进度三件套
- 已知风险或未解决问题：
  - 开发中发现 shell 中 `cd && uv run pytest` 复合命令偶发挂起，改用 python 内部 os.chdir 后稳定（不影响项目本身）
- 下一步最佳动作：BE-006 向量数据库抽象层（Chroma/Milvus 前置）

### Session 002
- 日期：2026-09-06
- 本轮目标：BE-002 后端配置管理
- 技术决策：
  - 配置统一走 pydantic-settings（`backend/app/config/settings.py`），业务代码通过 `get_settings()`（lru_cache 单例）读取，禁止散读环境变量。
  - 三个 Provider（DB/向量库/LLM）用 str Enum 表达，非法取值在启动时即被 pydantic 拒绝。
  - 敏感配置 GLM_API_KEY 只从环境变量注入，不落盘、不进日志；提供 `.env.example` 模板，真实 `.env` 由 gitignore 排除。
  - 启动时以结构化日志输出当前生效的 Provider（仅名称，无密钥）。
- 已完成：Settings 配置体系、Provider 枚举、.env.example、main.py 启动配置日志、4 个配置测试
- 运行过的验证：
  - `uv run pytest tests -q` → 5 passed
  - 真实启动：日志 `"Application configured", data={db_provider: sqlite, vector_store_provider: chroma, llm_provider: ollama}`，`curl /api/health` → ok
  - 环境变量切换 smoke：`DB_PROVIDER=mysql VECTOR_STORE_PROVIDER=milvus LLM_PROVIDER=glm` 启动后日志显示三者已切换，业务代码零修改
- 已记录证据：见 feature_list.json BE-002 evidence
- 提交记录：feat: BE-002 unified configuration management
- 更新过的文件或工件：docs/ARCHITECTURE.md（新增第 14 节）、backend/app/config/settings.py、backend/app/main.py、backend/.env.example、backend/tests/test_settings.py、progress.md、feature_list.json、session-handoff.md、clean-state-checklist.md
- 已知风险或未解决问题：无
- 下一步最佳动作：BE-003 后端分层与依赖注入架构

### Session 001
- 日期：2026-09-06
- 本轮目标：BE-001 后端项目基础框架
- 技术决策：
  - 按 ARCHITECTURE.md 将 pyproject.toml 从仓库根目录移至 `backend/`（根目录原为空占位文件），`.venv` 与 `uv.lock` 均位于 backend 内。
  - Python 锁定为 `>=3.11,<3.12`（uv 已安装 cpython 3.11.15）。
  - 结构化 JSON 日志在 `backend/app/common/logging.py` 统一实现，uvicorn 自身日志也归一为 JSON；`LOG_LEVEL` 默认 ERROR。
  - 应用入口采用 `create_app()` 工厂函数，为后续按配置装配 Provider 留扩展点。
  - 本轮只建立模块边界（api/application/domain/infrastructure/agent/config/common），未提前实现 BE-002 配置管理。
- 已完成：backend 骨架、FastAPI 入口 + /api/health、结构化日志、健康检查测试
- 运行过的验证：
  - `uv sync` 成功（fastapi 0.48+ / uvicorn 0.52.4 等）
  - `uv run pytest tests -q` → 1 passed
  - `LOG_LEVEL=INFO uv run uvicorn app.main:app ...` 真实启动成功，`curl /api/health` → `{"status":"ok"}`
  - 日志输出为单行 JSON：`{"timestamp": ..., "level": "INFO", "service": "system", "message": "Health check requested"}`
- 已记录证据：见 feature_list.json BE-001 evidence
- 提交记录：见 git log（feat: BE-001 backend base framework）
- 更新过的文件或工件：docs/ARCHITECTURE.md（新增第 13 节）、backend/**、progress.md、feature_list.json、session-handoff.md、clean-state-checklist.md、删除根 pyproject.toml
- 已知风险或未解决问题：无
- 下一步最佳动作：BE-002 后端配置管理（pydantic-settings 统一配置入口 + Provider 切换）
