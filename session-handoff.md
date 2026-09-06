# 会话交接

## 当前已验证

- 现在明确可用的部分：
  - DI 容器（app/common/di.py）+ 唯一装配点（app/containers.py），Database 已按 DB_PROVIDER 注册工厂并接入 main.py lifespan（启动自动建库/关闭释放）。
  - 数据库抽象层：domain/entities 纯 dataclass 实体（Conversation/Message/Document）、domain/repositories 三个接口、Database 抽象含事务上下文。
  - SQLite 实现：aiosqlite，建表幂等、外键级联、事务回滚、提交边界由 Database 层控制。
- 这轮实际跑过的验证：
  - `uv run pytest tests -q` → 18 passed
  - 删除 backend/data/law_agent.db 后真实启动自动重建，日志 "Database initialized"，curl /api/health → ok

## 本轮改动

- 新增了哪些代码或行为：
  - BE-003：DIContainer、create_container、test_di.py
  - BE-004：实体（conversation/message/document）、三个 Repository 接口、Database/TransactionContext 抽象、test_database_abstraction.py（内存 Fake）
  - BE-005：SQLiteDatabase（含三仓库）、test_sqlite_database.py、lifespan 自动建库、容器注册 Database
- 基础设施或 harness 发生了哪些变化：依赖新增 aiosqlite 0.22；docs/ARCHITECTURE.md 新增第 15-17 节

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：uvicorn 多 worker 并发下的 SQLite 写入竞争（当前单 worker，暂不构成问题）；MySQL 分支在容器中会抛 NotImplementedError（符合预期）
- 下一轮会话需要注意的风险：
  - 本机 Ollama 当前实际模型为 qwen3.5:9b，配置默认已改为 qwen3.5:4b（BE-010 验证前需拉取该模型或本机已存在时直接使用）
  - GLM_API_KEY 未设置（BE-010 的 GLM 真实调用验证可能受阻）
  - 本会话中 `cd xxx && uv run pytest` 复合命令偶发挂起（疑似 shell 权限确认），可用 `uv run --project backend` 或 python os.chdir 规避

## 下一步最佳动作

- 最高优先级未完成功能：BE-006 向量数据库抽象层
- 为什么它是下一步：BE-007 Chroma、BE-008 Milvus、BE-013 入库、BE-014 检索全部依赖 VectorStore 抽象
- 什么结果才算 passing：RAG 业务代码只依赖 VectorStore 抽象接口，不直接调用 Chroma API，接口有 Fake/测试证据
- 这一步中哪些东西不要动：Database 抽象与 SQLite 实现的提交边界设计（_tx_depth 机制）；di.py 的双重检查锁

## 命令

- 启动命令：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 验证命令：`cd backend && uv run pytest tests -q`
- 定向调试命令：`LOG_LEVEL=INFO uv run uvicorn app.main:app --port 8000`
