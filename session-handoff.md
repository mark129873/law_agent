# 会话交接

## 当前已验证

- 现在明确可用的部分：backend/ DDD 分层骨架 + FastAPI 入口 + `/api/health`；统一配置系统（`app/config/settings.py`，pydantic-settings），三个 Provider（DB_PROVIDER/VECTOR_STORE_PROVIDER/LLM_PROVIDER）均可通过环境变量或 backend/.env 切换，业务代码零修改；结构化 JSON 日志全链路生效。
- 这轮实际跑过的验证：
  - `uv run pytest tests -q` → 5 passed（含 4 个配置测试）
  - 真实启动：`curl /api/health` → 200，启动日志 `"Application configured"` 记录默认 provider sqlite/chroma/ollama
  - 环境变量切换：设置 mysql/milvus/glm 后启动日志确认三个 provider 均已切换

## 本轮改动

- 新增了哪些代码或行为：`app/config/settings.py`（Settings + Provider 枚举 + get_settings 单例）、`.env.example`、`tests/test_settings.py`、main.py 启动配置日志
- 基础设施或 harness 发生了哪些变化：docs/ARCHITECTURE.md 新增第 14 节配置管理；backend 依赖新增 pydantic-settings 2.15

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：provider 枚举尚未被任何基础设施实现消费（BE-004 起接入）；.env 文件实际加载未测（当前仓库无 .env）
- 下一轮会话需要注意的风险：测试覆盖配置时须直接构造 Settings（`_env_file=None`），不要走 get_settings 的 lru_cache；8000 端口占用会报 10048

## 下一步最佳动作

- 最高优先级未完成功能：BE-003 后端分层与依赖注入架构
- 为什么它是下一步：BE-004~BE-010 的所有基础设施实现都需要通过依赖注入装配到业务层，BE-003 是它们的地基
- 什么结果才算 passing：核心业务层不直接依赖 SQLite/Chroma/Ollama/GLM 具体实现，依赖通过注入/工厂管理，并有测试证据
- 这一步中哪些东西不要动：已验证的启动路径、/api/health、settings.py 的字段命名（后续实现将按此读取）

## 命令

- 启动命令：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 验证命令：`cd backend && uv run pytest tests -q`
- 定向调试命令：`LOG_LEVEL=INFO uv run uvicorn app.main:app --port 8000`（查看 JSON 日志与生效 provider）
