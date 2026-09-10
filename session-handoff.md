# 会话交接

## 当前已验证
- 现在明确可用的部分：
  - **后端 BE-001~027 全部 passing**（最新 BE-027：结构化日志落盘 `backend/log/` 与日志规则强化）。
  - **前端 FE-001~012 全部 passing**（含 FE-012：侧边栏历史对话旧在上新在下）。
  - **测试体系**：后端自动化 117 个（2026-09-10 全绿）；端到端脚本 3 个（依赖本机 Ollama，手工运行）。
- 最近一轮实际跑过的验证（2026-09-10，Session 024，BE-027 日志落盘）：
  - `uv run pytest -q` → 117 passed（基线 106）；分层 unit 48 / integration（除 API）60 / API 9
  - 干净环境（先删 `backend/data`）跑全量通过
  - 真实启动实测（8011 端口）：删 `backend/log` → 启动自动创建并写入 `app.log`（单行 JSON，`timestamp` 形如 `2026-09-10T09:37:50.369Z`）；带 `X-Request-ID: verify-001` 请求 `/api/health` 后日志带 `request_id=verify-001`；验证后进程与端口已清理

## 本轮改动（Session 024：BE-027 日志落盘与规则强化）
- `docs/RELIABILITY.md`：日志规则全面强化——双 sink（stdout + 文件）、落盘目录 `backend/log/`、按天轮转与保留 30 天、目录自愈、**写盘失败降级为仅 stdout**、`setup_logging` 幂等、service 受控清单、字段契约（`request_id` / ERROR 带堆栈 / 字段只增不改）、敏感键脱敏兜底、日志契约测试；时间戳与实现对齐为 UTC 毫秒 + `Z`；默认等级 `ERROR → INFO`
- 代码：`app/common/logging.py`（双 sink + `TimedRotatingFileHandler` + 目录自愈 + `OSError` 降级 + 幂等关闭 + UTC 毫秒 Z + `WARNING→WARN` + 敏感键脱敏 + `RequestContextFilter`/ContextVar）；新增 `app/api/middleware.py`（纯 ASGI `RequestIdMiddleware`，避免 BaseHTTPMiddleware 破坏 SSE）；`settings.py`（`log_level` 默认 INFO + `log_dir`/`log_file_name`/`log_backup_count` + `resolved_log_dir`）；`main.py`（`create_app` 首行 `setup_logging(settings)` + 注册中间件）；新增 `tests/conftest.py`（测试日志隔离到系统临时目录）与 `tests/unit/test_logging.py`（9 例契约测试）
- 配置与忽略：`.env.example` 新增日志配置段；`.gitignore` 新增 `backend/log/`
- 文档同步：`ARCHITECTURE.md` §2（`api/middleware.py`、common 落盘、`log/` 目录）、§6（配置表 + 日志配置说明）、§8（日志行）、§9（48/60/9，合计 117）；`feature_list.json` BE-027；`init.md` 测试数量 117；`clean-state-checklist.md` 增加 `backend/log` 未提交校验

## 仍损坏或未验证
- 已知缺陷：无
- 未验证路径：
  - MySQL 8.0 真实接入（驱动、URL 分支、真实实例集成测试、增量迁移方案）——只做到"方言无关 + 容器显式拒绝"，无任何 MySQL 实机验证
  - 连接池化（每请求一会话/连接）——当前仍是单会话，端口形状与池化模型不兼容，属独立改造
  - 前端本轮未改动（未重跑 `npm run build`；API 契约与 SSE 协议未变，HTTP 层由 8 个接口测试覆盖）
  - 端到端脚本（真实 Ollama）与浏览器 E2E 本轮未执行
- 下一轮会话需要注意的风险：
  - **数据目录现在会被自动重建，但内容不会回来**：`backend/data/` 已被清空（旧的历史会话/文档数据不复存在），当前是空库；`tests/data_source/` 里的真实法律文档仍在，可重新上传
  - **测试干净环境流程**（RELIABILITY.md）：开工/收尾测试前删除 `backend/data/`
  - **ORM 新增的维护面**（已有 6 个契约测试锁住，但仍是新成本）：实体与 ORM 模型两套定义（字段增删要同时改 `models.py` 与 `mappers.py`）；session 状态语义（identity map、过期对象、批量操作需显式 `synchronize_session`）；异步 ORM 必须保持 `expire_on_commit=False`，否则提交后访问对象属性会抛 `MissingGreenlet`
  - 文档状态更新多了一次 SELECT（属性级更新换 identity map 一致性），属明确取舍
  - 同一 `created_at` 无第二排序键（用户指定"仅按时间判断"）：重复查询稳定，但插入先后不再保证
  - Ollama 0.32.0 偶发缺陷仍在：上传（embedding 批处理）后立即提问可能 500（后端已转为 SSE error 事件）
  - Windows 下 TaskStop/taskkill 可能超时或留孤儿进程占用 8000：`netstat -ano | grep :8000` 找 PID 后用 PowerShell `Stop-Process -Force`；Git Bash 偶发 `uv` 找不到（exit 127），重试即可
  - 浏览器 IAB 上传不走系统文件选择框：用页面内 DataTransfer 构造 File 派发 input change
  - min_score 默认 0.0（不过滤）；E2E 脚本依赖本机 Ollama（qwen3.5:4b / nomic-embed-text:latest）与 .env 中 GLM_API_KEY

## 下一步最佳动作
- 若继续做数据库方向：MySQL 8.0 接入（`uv add aiomysql` → `containers.py` 增加 `mysql+aiomysql://…` URL 分支 → 真实实例跑同一批契约测试 → Alembic autogenerate 可直接消费现有声明式模型），属独立功能，需在 feature_list.json 立项
- 可选产品增强（需用户决定）：会话重命名（需 PATCH 端点）、回答停止按钮（需取消协议）、深色主题手动开关、部署方案与 CORS 收敛、OllamaProvider 加重试
- 这一步中哪些东西不要动：后端 API 契约（ARCHITECTURE.md 第 7 节表格与 SSE 协议含 sources）；统一错误结构 {code,message}；前端 api/state 分层与主题 token 体系；messages.sources 的存储格式（JSON 数组 [{source,content}]）；`IsoDateTime` 的 ISO-8601 存储格式（改了会让旧库时间无法回读）；领域层零技术依赖（ORM 模型不得进入 domain，守护测试会拦）；**数据存放位置**（用户明确要求保持 `backend/data/`，不要改锚点或写死绝对路径）

## 命令
- 后端启动：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 干净环境重置（RELIABILITY.md 规定，测试前后各做一次）：删除 `backend/data/`（启动时会自动重建，BE-026）
- 后端验证：`cd backend && uv run pytest`（全量 106 个）；分层：`pytest tests/unit` / `pytest tests/integration`
- 数据落点确认：`Get-ChildItem backend\data -Force`（应看到 `law_agent.db` 与 `chroma\`）
- 前端构建：`cd frontend && npm install && npm run build`（tsc 类型检查 + vite）
- 前端启动：`cd frontend && npm run dev`（http://localhost:5173，/api 代理到后端 8000；联调需先启动后端）
- 端到端（需本机 Ollama）：启动服务器后 `PYTHONPATH=backend python backend/scripts/verify_real_e2e.py`
- 定向调试：`LOG_LEVEL=INFO uv run uvicorn app.main:app --port 8000`；OpenAPI http://127.0.0.1:8000/docs
