# progress.md -- 会话进度日志

## 当前已验证状态
- 仓库根目录：`C:\Users\nnnnnn\Desktop\law_agent`
- 标准启动路径：`cd backend && uv sync && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 标准验证路径：`cd backend && uv run pytest tests -q`（全量 117 个自动化测试）；启动后 `curl http://127.0.0.1:8000/api/health`
- 当前最高优先级未完成功能：无——BE-001~027 与 FE-001~012 全部 passing
- 当前 blocker：无

### Session 024（BE-027 结构化日志落盘 backend/log + 日志规则强化）
- 日期：2026-09-10
- 本轮目标：用户要求"分析 RELIABILITY.md 日志规则可优化点"并"将日志落盘到 backend/log"；先改文档（RELIABILITY.md 已完成强化），再落地代码
- 技术决策：
  - 双 sink 复用同一 `JsonFormatter`：stdout 供开发/容器采集，`backend/log/app.log` 供事后追溯，避免两处格式漂移
  - 落盘用标准库 `TimedRotatingFileHandler`（when=midnight、utc=True、backupCount 可配、encoding=utf-8、delay=True），不引入第三方依赖；按天轮转便于"找某天的日志"
  - 目录锚定复用 `settings._anchor_path`，新增 `resolved_log_dir`（与 data/ 同一套机制，不随启动目录漂移）；目录不存在时 `mkdir(parents=True, exist_ok=True)` 幂等自愈
  - **失败降级为硬要求**：`mkdir`/建 handler 抛 `OSError` 时只保留 stdout，绝不向上抛——日志故障不得把业务变成 5xx（同类于历史 extra 保留字段 404→500 事故）
  - `setup_logging(settings)` 统一经配置读取（消除三处不一致：logging.py 直接 os.getenv、`.env` 的 LOG_LEVEL 实际不生效、settings.log_level 是死字段）；重复调用先 close+remove 旧 handler（Windows 下不关闭会占用文件句柄）
  - 时间戳统一 UTC 毫秒 + `Z`（原实现是微秒 + `+00:00`，与文档示例不符）；`WARNING` 归一为 `WARN`；`service` 采用受控清单
  - request_id 用**纯 ASGI 中间件 + ContextVar**：刻意不用 `@app.middleware("http")`（BaseHTTPMiddleware 会缓冲响应体、破坏 SSE 流式）；响应头回写 `x-request-id`，请求头传入则沿用
  - 敏感键脱敏作为"密钥禁止进日志"的机械兜底；默认等级 ERROR→INFO（解决"INFO 用于重要业务事件却默认不可见"的矛盾）
  - 测试产物隔离：新增 `tests/conftest.py`，在导入应用代码前把 `LOG_DIR` 指向系统临时目录，避免 pytest 往仓库写日志
- 运行过的验证：
  - `uv run pytest -q` → **117 passed**（基线 106；新增 `tests/unit/test_logging.py` 9 例 + test_settings 日志默认值与 resolved_log_dir 锚定 + test_api x-request-id 生成与透传）
  - 干净环境（先删 `backend/data`）跑全量，分层：unit 48、integration（除 API）60、API 9
  - 真实启动实测（8011 端口）：删 `backend/log` → 启动自动创建 `backend/log/app.log`；日志为标准单行 JSON（`timestamp` 形如 `2026-09-10T09:37:50.369Z`）；带 `X-Request-ID: verify-001` 请求 `/api/health` 后，`Health check requested` 与 `uvicorn.access` 两条日志均带 `request_id=verify-001`；验证后进程与 8011 端口已清理
- 已记录证据：feature_list.json BE-027（passing）；RELIABILITY / ARCHITECTURE / .env.example / .gitignore / init.md / clean-state-checklist 同步
- 提交记录：本轮提交
- 已知风险或未解决问题：
  - 默认等级改为 INFO 会增加输出量（属行为变化，已按分析建议确定，需要时可经 `LOG_LEVEL` 调回）
  - 多 worker 部署时按天轮转会竞争同一文件，文档已注明需改按 PID 分文件或集中采集（当前单进程，不触发）
  - 既有遗留项不变：MySQL 未启用、无连接池、同一 created_at 无第二排序键、Ollama 偶发上传后提问 500
- 下一步最佳动作：可选产品增强（会话重命名 / 停止按钮 / 深色主题开关 / CORS 收敛 / OllamaProvider 重试）或 MySQL 8.0 接入

### Session 023（文档整理：PRODUCT.md 只留产品描述，架构内容归 ARCHITECTURE.md）
- 日期：2026-09-10
- 本轮目标：用户要求"整理 PRODUCT.md，将与产品描述无关的内容去除，架构方面的整理到 ARCHITECTURE.md 中"
- 做了什么：
  - **PRODUCT.md 重写为纯产品描述**：新增开头的文档职责声明（本文件只写用户可见行为；实现/架构见 ARCHITECTURE.md；行为要变先改本文件），并把原有条目按功能域重组为 5 节——1 产品定位、2 知识库（文档）、3 对话、4 参考文档（回答依据展示）、5 视觉与交互风格
  - **移除 3 条架构/实现内容**（这些内容在 ARCHITECTURE.md 已有或已补对应位置）：
    ① "三处排序统一由应用服务层按 created_at 决定、与数据库实现无关" → ARCHITECTURE §3「排序职责（BE-024）」并新增"产品要求出处"一条做交叉引用
    ② "后端数据库访问使用 SQLAlchemy ORM（声明式模型 + 领域实体映射）" → ARCHITECTURE §3「ORM 使用约定（BE-025）」
    ③ "清空数据目录后首次启动自动重建目录与数据库文件" → ARCHITECTURE §6「数据目录自动创建」与 §8「首次启动自愈（BE-026）」
  - **顺手去实现化措辞**（不改变用户可见语义）：上传条目的"会被解析为向量并存储到向量数据库中"改为"会被解析并纳入知识库，供问答检索使用"；参考文档条目的"参考来源随回答一起持久化"改为用户可感知的"刷新或重新打开会话后仍可查看"
  - **ARCHITECTURE.md §0 新增文档职责声明**：本文档只描述架构与实现，用户可见行为需求见 PRODUCT.md；实现变更不得改变 PRODUCT.md 描述的行为——从制度上防止两份文档再次互相渗透
- 逐条核对：原 PRODUCT.md 的 22 行里，除上述 3 条实现说明外，其余产品要求**全部保留**（上传格式/知识库视图/文档明细与删除/新建与切换会话/首问定标题/新建回跳/流式回复/删除会话/三处排序/参考文档显示与不显示/视觉风格），无遗漏
- 运行过的验证：
  - 文档改动未触及代码；按 RELIABILITY.md 干净环境（`backend/data` 不存在）跑 `uv run pytest` → **106 passed**
  - 确认 ARCHITECTURE.md 覆盖被移除的三条内容（§3、§6、§8 均有对应小节），并已用交叉引用指明出处
- 已记录证据：本轮为文档整理，feature_list.json 无功能状态变化（BE-001~026 与 FE-001~012 保持 passing）
- 提交记录：本轮提交
- 已知风险或未解决问题：无新增；数据库方向的遗留项（MySQL 未启用、连接池未引入）与 ORM 维护面同前
- 下一步最佳动作：可选产品增强（会话重命名 / 停止按钮 / 深色主题开关 / CORS 收敛 / OllamaProvider 重试）或 MySQL 8.0 接入，均需先立项

### Session 022（BE-026 修复数据目录缺失时首次启动无法建库）
- 日期：2026-09-10
- 本轮目标：用户按新的开工流程清空 `backend/data/`（见 RELIABILITY.md 的"测试干净环境管理"）后发现标准启动路径失败，定位并修复该回归
- 问题与根因：
  - 现象：`SQLAlchemyDatabase.connect()` + `init_schema()` 抛 `sqlite3.OperationalError: unable to open database file`
  - 根因：BE-024 把手写 SQL + aiosqlite 实现重写为 SQLAlchemy 时，丢失了原 `connect()` 里的 `self._db_path.parent.mkdir(parents=True, exist_ok=True)`；SQLite 不会自行创建父目录
  - 为什么既有测试没抓到：106 个测试全部使用 pytest `tmp_path`（目录必然存在），没有任何用例覆盖"父目录不存在"；Chroma 侧本来就有 `mkdir`，所以只有数据库这一侧受影响
  - 影响面：按 RELIABILITY.md 的流程，每次开工/收尾测试前都会删 `backend/data/`，等于每次都命中，属必须先修的基础状态问题
- 技术决策：
  - 修复放在**数据库实现内部**（`_ensure_sqlite_parent_dir()` + `connect()` 首行调用），而不是启动脚本或容器工厂：数据目录属存储细节，放实现里则任何入口（uvicorn、测试、将来的 CLI）都自动获得自愈能力，不需各自记得建目录
  - 只处理文件型 SQLite：`make_url(url).get_backend_name() == "sqlite"` 且非 `:memory:`；MySQL 的 URL 里是库名不是路径，目录由部署负责
  - 路径用 `make_url(url).database` 解析（只读实测：Windows 绝对路径 → `C:/.../law_agent.db`、相对路径 → `data/law_agent.db`、`:memory:` 原样、MySQL 跳过），因此锚定到 `backend/` 的相对路径与绝对路径都正确
  - `mkdir(parents=True, exist_ok=True)` 幂等（与 `init_schema()` 幂等建表同一思路）；只在目录真的不存在时打一条结构化 INFO 日志 `Database directory created`，避免每次启动刷屏
- 已完成：`database.py` 修复 + 2 个回归测试 + 文档同步（ARCHITECTURE §6/§8/§9、PRODUCT 实现说明、feature_list BE-026 与 BE-005 说明、init.md 测试数量）
- 运行过的验证：
  - `uv run pytest` → **106 passed**（基线 104，既有断言一行未改）；分层：unit 38、integration 60（28.21s）、api 8
  - 新增回归测试：`test_connect_creates_missing_data_directory`（多层目录都不存在 → 建库成功且可读写；重复连接同路径仍可用）、`test_clean_environment_reset_then_start_again`（建库写入 → 删除整个 data 目录 → 再次启动得到可用空库）
  - 真实启动两轮（干净环境流程复现）：删除 `backend/data`（确认不存在）→ `uv run uvicorn app.main:app` → 自动创建 `data/`、`law_agent.db`（32768 字节）与 `data/chroma/`；日志 `Database directory created` → `Database initialized` → `VectorStore initialized`；`/api/health` ok、`/api/conversations` 与 `/api/documents` 均为 0；`POST /api/conversations` 201 → `DELETE` 204（回到 0）。**再删一次 data 目录重启，第二轮同样自愈**（证明可重复）
- 已记录证据：feature_list.json BE-026（passing，含修复前复现与修复后两轮实测数据）；BE-005 evidence 补充说明
- 提交记录：本轮提交
- 顺带说明：数据存放位置**保持不变**（仍为 `backend/data/law_agent.db` 与 `backend/data/chroma`）——用户明确要求本轮不改位置；关于"改到仓库根 `data/`"的两种方案（`.env` 覆盖 / 改 `_PROJECT_ROOT` 锚点为 `parents[3]`）已在会话中给过评估，未实施
- 已知风险或未解决问题：
  - 同一 `created_at` 无第二排序键（用户指定"仅按时间判断"，沿用）；MySQL 未启用、连接池未引入（同前）
  - ORM 维护面（两套模型 + 映射层、session 状态语义）同前，已有 6 个契约测试锁定
- 下一步最佳动作：可选产品增强（会话重命名 / 停止按钮 / 深色主题开关 / CORS 收敛 / OllamaProvider 重试）或 MySQL 8.0 接入，均需先立项

### Session 021（BE-025 数据库访问改造为 SQLAlchemy ORM）
- 日期：2026-09-10
- 本轮目标：用户询问"用 SQLAlchemy ORM 是不是更好"，在评估结论为"本项目不划算"后仍选定**改成 ORM（最小代价路径）**
- 技术决策：
  - 最小代价路径 = 不动领域层、不动 `Database`/三个 Repository 端口、不动应用服务层（排序仍在应用层按 created_at 判断），只替换 infrastructure 内部实现
  - 新增 `models.py`（DeclarativeBase + 三个声明式模型，取代 Core 的 `schema.py`）与 `mappers.py`（Data Mapper：`to_domain_*` / `to_model_*` 双向映射，sources 的 JSON 编解码集中此处）
  - `async_sessionmaker(expire_on_commit=False)` + 单个 `AsyncSession` 取代裸连接：仍是"进程级单连接"语义，**不引入连接池**（池化会改端口形状，属独立改造）。`expire_on_commit=False` 是异步 ORM 的必要设置，否则 commit 后访问属性会抛 `MissingGreenlet`
  - 事务栈守卫提交边界的契约完全保留：最外层优先复用 autobegin 事务（"先读后开事务"可用）、嵌套 SAVEPOINT、异常回滚丢弃全部写入
  - 仓储写法：`session.add` / `session.get` / 属性赋值更新（文档状态），消息按会话删除保留批量 `delete` 并显式 `synchronize_session="fetch"`（需要影响行数、避免 N+1、防止 session 残留已删除对象）
  - **刻意不定义 relationship**：本项目无聚合内导航需求（消息永远按 conversation_id 显式查询），不定义关系就没有异步懒加载风险；级联删除由表级 `ON DELETE CASCADE` 保证
  - 明确接受的一处取舍：文档状态更新从 Core 的批量 UPDATE 改为"取出模型→改属性"，多一次 SELECT，换来 identity map 与数据库始终一致（否则"更新后回读"会拿到过期状态）
- 运行过的验证：
  - `uv run pytest -q` → **104 passed**（基线 98；新增 `tests/integration/test_orm_contract.py` 6 例）；分层：unit 38（~2s）、integration 58（25.63s）、api 8
  - ORM 特有契约（新增测试锁定）：仓储出口精确为领域 dataclass 且非 ORM 模型、`expire_on_commit=False` 下提交后仍可读属性（默认配置下该访问会抛 `MissingGreenlet`）、状态属性级更新后同一会话回读非过期值、批量删除后 session 无残留、事务回滚能撤销属性级更新、数据库实例持有唯一会话
  - BE-024 全部行为断言原样通过（持久化/外键级联/事务提交与回滚/先读后事务/建表幂等/旧库补列迁移/来源往返/时间保留时区/乱序落库按时间排序）
  - 旧库兼容实测（迁移前版本创建的 `backend/data/law_agent.db`）：标准启动 `/api/health` ok、会话 4 条按 created_at 正序、文档 4 条按上传时间倒序、首条会话消息 user→assistant、`POST` 201（4→5）→ `DELETE` 204（回到 4，测试会话已清理）
  - 旧库零破坏复核（只读 sqlite_master/PRAGMA）：三表定义未变、`sources` 列在、外键 `ON DELETE CASCADE` 在、`idx_messages_conversation` 在、行数 4/8/4 与验证前一致 → ORM 的 `create_all` 对既有表零改动
- 已记录证据：feature_list.json BE-025（passing）、BE-024 与 BE-005 evidence 补充"实现载体已改造为 ORM"的说明；NEW_FEATURE.md 记录本轮功能与实测结果；ARCHITECTURE.md 新增"ORM 使用约定"小节
- 提交记录：本轮提交
- 已知风险或未解决问题：
  - ORM 带来的固有复杂度已确认并记录在案：多一层实体↔模型映射（字段增删需同时改 models/mappers）、session 状态语义（identity map、过期对象）、批量操作需显式同步策略。本轮用 6 个契约测试把这些点锁住，但它们是新引入的维护面
  - 仍未引入连接池（单会话/单连接）；MySQL 仍未启用（容器对 `DB_PROVIDER=mysql` 显式 NotImplementedError），接入只剩装 aiomysql + URL 分支 + 真实实例验证
  - 同一 `created_at` 仍无第二排序键（沿用用户指定口径：仅按时间判断）
- 下一步最佳动作：MySQL 8.0 接入（驱动 + URL 分支 + 真实实例集成验证 + Alembic autogenerate 可直接消费现有声明式模型），或 session-handoff 中列出的可选产品增强

### Session 020（BE-024 数据库实现迁移到 SQLAlchemy + 排序职责上移应用层）
- 日期：2026-09-10
- 本轮目标：用户提问"数据库的代码可以改为 sqlalchemy 么"并选定方案——改用 SQLAlchemy Core（async）替换手写 SQL + aiosqlite，同时**排序逻辑放到 application 层且仅按时间判断**
- 技术决策：
  - 选 SQLAlchemy 2.0 **async Core** 而非 ORM：本项目查询全是简单 CRUD，领域实体已是干净 dataclass，引入 ORM 会多一层 Row↔实体映射并带来 AsyncSession/expire_on_commit/异步懒加载等与"每次写入即提交"模型冲突的复杂度；Core 恰好解决真正的问题——方言差异（为 MySQL 8.0 接入清障）
  - 新增 `app/infrastructure/database/sqlalchemy/`（schema.py 表元数据 / types.py IsoDateTime / database.py 端口实现 + 三个仓储），删除 `database/sqlite/` 与已无用的 `mysql/` 空占位包；**aiosqlite 保留**（降级为 SQLAlchemy 的 SQLite 异步驱动，业务代码不再直接导入）
  - 时区无损：SQLAlchemy 默认 DateTime 在 SQLite 会丢 tzinfo、MySQL DATETIME 无时区概念，会让既有断言"读回 tzinfo 必须存在"失败；故用 TypeDecorator 继续以 ISO-8601 字符串存取（与旧实现逐字节一致，旧库零迁移）
  - 写进表级的方言无关细节：主键/外键用定长 VARCHAR（MySQL 的 TEXT 不能做主键/外键）、ForeignKey(ondelete="CASCADE") 生成表级约束（列内联 REFERENCES 在 MySQL 会被忽略）、SQLite 用 connect 事件开 `PRAGMA foreign_keys`
  - 排序上移：三个 Repository 去掉 ORDER BY（移除 SQLite 专有 rowid 第二排序键），ConversationService.list_conversations/get_messages 按 created_at 正序、DocumentService.list_documents 按 created_at 倒序；仓储端口文档改写为"不承诺顺序"。顺带修掉内存 Fake（倒序）与真实实现（正序）此前的排序不一致
  - 事务语义保持：单连接 + 事务栈守卫提交边界；最外层优先复用 SQLAlchemy 的 autobegin 事务（否则"先读后开事务"会抛 already begun），嵌套用 SAVEPOINT
- 运行过的验证：
  - `uv run pytest -q` → **98 passed**（迁移前基线 92；新增事务一次性提交、先读后事务、排序契约 4 例等共 6 例）；分层：unit 38（1.84s）、integration 52（21.97s）、api 8
  - 旧库兼容实测：用**迁移前版本创建**的 `backend/data/law_agent.db` 走标准启动路径 → `/api/health` ok；`GET /api/conversations` 4 条按 created_at 正序、`GET /api/documents` 上传时间倒序、中文与 sources JSON 无损（时间戳带 +00:00）；`POST /api/conversations` 201（4→5）→ `DELETE` 204（回到 4，测试会话已清理）；结构化 JSON 日志正常
  - 旧 schema 迁移：test_schema_migration_adds_sources_column 用同步引擎造 FE-023 之前的旧表 + 历史数据，验证幂等补列、数据保留、迁移后可写带来源消息
  - DDD 守护更新：`test_ddd_boundaries.py` 的技术库名单加入 sqlalchemy（aiosqlite 保留），sqlalchemy 只出现在 infrastructure
- 已记录证据：feature_list.json BE-024（passing）、BE-005 与 FE-012 evidence 同步更新；NEW_FEATURE.md 记录本轮功能与实测结果
- 提交记录：本轮提交
- 顺带修复：`feature_list.json` 在 FE-012 条目处缺逗号，导致整个文件无法被 JSON 解析（已修复并校验）
- 已知风险或未解决问题：
  - 同一 `created_at`（微秒级相同）时不再有第二排序键：顺序由底层返回顺序决定，`sorted` 稳定性保证重复查询一致，但"插入先后"不再被保证（本轮用户明确要求仅按时间判断；实际写入均间隔一次 IO，同微秒概率极低）
  - MySQL 仍未启用：容器对 `DB_PROVIDER=mysql` 显式抛 NotImplementedError（接入只剩装 aiomysql + URL 分支 + 真实实例验证）；连接池化事务模型（每请求一连接）与当前 `transaction()` 端口形状不兼容，属独立改造
- 下一步最佳动作：MySQL 8.0 接入（驱动 + URL 分支 + 真实实例集成验证 + 迁移方案如 Alembic），或 session-handoff 中列出的可选产品增强

### Session 019（FE-012 侧边栏历史对话正序）
- 日期：2026-09-06
- 本轮目标：用户要求侧边栏历史对话按创建时间从上到下；经确认方向为旧在上、新在下（此前为最新在上）
- 技术决策：
  - 先更新文档再写代码：PRODUCT.md 加排序行为条目；ARCHITECTURE.md 第 7 节对话列表倒序→正序；feature_list.json 新增 FE-012（in_progress 起步，FE-005 的 passing 记录不动）
  - 后端 SQLite 会话列表 `ORDER BY created_at ASC, rowid ASC`（rowid 兜底同秒稳定的顺序）；前端 createConversation 由顶部插入改为底部追加；文档列表保持倒序不动（用户未要求，窄范围）
  - 同步更新 test_api.py 正序断言（原倒序期望）；其余测试无顺序依赖
- 运行过的验证：
  - uv run pytest → 92 passed；npm run build 通过
  - 重启后端生效后真实浏览器验证：API 顺序与侧边栏从上到下完全一致（旧→新，新建会话在底部），测试会话已清理
  - 运维备注：Git Bash 无 Stop-Process，用 powershell.exe -Command 停旧 uvicorn；nohup 后台启动新后端
- 提交记录：本轮提交
- 下一步最佳动作：可选增强（会话重命名/停止按钮/深色主题手动开关/部署收敛/OllamaProvider 重试），需用户决定

### Session 018（FE-011 浏览器端到端验证收尾）
- 日期：2026-09-06
- 本轮目标：按 AGENTS.md 启动流程接续，完成 FE-011 最后一项验证并置 passing
- 按流程执行：pwd 确认目录；重读 ARCHITECTURE/PRODUCT/RELIABILITY/progress/handoff/feature_list/init/NEW_FEATURE（NEW_FEATURE 与 PRODUCT/feature_list 已同步，无需再改）；init 文件存在性全部通过；后端 uv run pytest → 92 passed；前端 npm run build 通过；后端 :8000 与前端 :5173 均为运行中（health ok/200）
- 技术决策：
  - 本机无 Chrome，用 playwright-core + 本机 Edge（executablePath 直指 msedge.exe，headless）做真实浏览器验证；脚本与截图放在仓库外 Temp/opencode/fe011/（verify-fe011.cjs + 3 张截图），仓库零污染，不改 package.json
  - 空知识库场景需清空向量库：经 API 临时删除唯一文档（专利法 txt），测后即用 tests/data_source 原文件重传恢复 ready；向量由同内容重建，测试会话事后按标题清理
- 运行过的验证（真实浏览器）：
  - A1 RAG 提问专利法期限：流式完成后「参考文档」按钮出现（计数 4）
  - A2 点击展开：按序号列表，首项为专利法 txt 及第二十六条命中内容
  - A3 刷新后重进会话：按钮仍在（持久化恢复链路贯通）
  - B 空知识库无关提问：参考文档按钮数量为 0
  - 契约层复验：真实 SSE sources 事件先于全部 delta，持久化来源与流内一致，GET 回读一致
  - 收尾复检：文档恢复为 1 个 ready；后端 pytest 92 passed
- 附带问题：清理测试会话时按标题前缀删除，误删 1 条历史同名专利法提问会话（属测试数据；用户保留的 2 条历史会话未动）
- 提交记录：本轮提交
- 下一步最佳动作：可选增强方向（需用户决定）：会话重命名、回答停止按钮、深色主题手动开关、部署收敛 CORS；或 OllamaProvider 加重试解决上传后立即提问偶发 500 的已知风险

### Session 017（参考文档功能 BE-023/FE-011）
- 日期：2026-09-06
- 本轮目标：NEW_FEATURE.md——RAG 回答后显示「参考文档」按钮，点开按序号展示参考文档与内容；未使用检索或无命中不显示
- 技术决策：
  - 后端 BE-023：domain/services/qa_workflow.py 新增 QaStreamEvent 值对象（delta/sources 二态）；RetrieveNode 检索命中时经 get_stream_writer 推送 sources（先于全部 delta，数组顺序即展示序号；Prompt 依据与前端展示同源）；ChatService 收集来源随回答一起持久化；messages 表新增 sources JSON 列（init_schema 幂等 ALTER 迁移旧库，历史数据保留）；MessageResponse/消息接口返回 sources；SSE 协议新增 sources 事件
  - 前端 FE-011：types 新增 ReferenceSource；chat.ts 增加 onSources 回调；AppContext 在 done 时挂载 sources（生成中不挂载，回答完成后按钮才出现）；MessageBlock 参考文档折叠按钮（Phosphor Books 图标 + 计数徽标 + 按序号列表，来源内容纯文本渲染不进 Markdown，ref-panel-in 入场动画 respects prefers-reduced-motion，aria-expanded 无障碍属性）
  - RagService 拆出纯函数 format_context：检索节点同一批 chunk 既组装 Prompt 上下文又组装参考来源，二者天然同源不漂移
- 运行过的验证：
  - 后端 uv run pytest → 92 passed（新增 6 例：sources 事件先于 delta 且持久化回读、图级有命中推送/无命中不推、旧库迁移幂等、消息来源往返）
  - 前端 npm run build（tsc 类型检查 + vite）通过
  - 测试夹具修复：API 测试容器入库与检索必须注入同一确定性 embedding（此前只替换检索侧，入库仍走真实 Ollama embedding，维度 768 vs 64 不一致导致检索报错且测试悄悄触网）
  - scripts/verify_real_e2e.py 增加 sources 事件与持久化断言
  - 浏览器端到端验证：本轮最后一步执行（空知识库无按钮 / RAG 有按钮可展开 / 刷新恢复）
- 提交记录：本轮提交
- 下一步最佳动作：浏览器端到端验证后 FE-011 置 passing

### Session 016（全项目全面测试轮）
- 日期：2026-09-06
- 本轮目标：按用户要求做全项目全面测试（单元/集成/接口/端到端/前端界面）
- 测试结果：
  - 后端单元 tests/unit → 38 passed
  - 后端集成+接口 tests/integration（含 test_api.py 7 例接口测试）→ 48 passed
  - 后端全量 uv run pytest → 86 passed
  - 端到端 scripts/verify_real_e2e.py：干净环境通过（上传 201 ready ×2 → RAG 回答逐字引用第四十二条并标注来源 → user/assistant 持久化）
  - 前端 npm run build（tsc+vite）通过；浏览器 GUI 黑盒走查 T1~T9 全部通过（截图证据归档 gui-test-screenshots/，已 gitignore）：加载渲染/空输入禁用/建议填充启用/流式生成中状态/回答引用/会话往返恢复/知识库汇总与明细/跨视图新对话跳转/删除确认取消与删除两路径/超长输入 160px 封顶
- 本轮发现并处理的问题：
  - 【已处理】测试数据污染：专利法文档被历次测试重复上传 3+ 份，向量库重复 chunk 导致检索退化（回答上下文错引第二十六/二十七条）。按 RELIABILITY.md 干净环境规则重置 backend/data 后重跑，检索质量恢复
  - 【已记录】瞬态缺陷：Ollama 0.32.0 在"上传触发 embedding 批处理后立即提问"的模型切换窗口偶发对 /api/chat 返回 500（复现 1/2 次）；后端按设计转为 SSE error 事件，前端错误条正常展示。属 Ollama 侧健壮性问题，可在后端加重试，暂记录为已知风险
- 运维备注：taskkill 在本机偶发超时，PowerShell Stop-Process 可靠；测试期间多次遇到 IAB 点击抖动，改用 CUA 坐标点击 + 只读几何定位（getBoundingClientRect）后稳定
- 提交记录：本轮提交

### Session 015（LLM 思考模式开关）
- 日期：2026-09-06
- 本轮目标：新增 .env 配置项控制 LLM think 开关，默认关闭（应用户需求）
- 技术决策：
  - 新增 `LLM_ENABLE_THINKING`（bool，默认 False）：关闭时 Ollama 请求携带顶层 `think:false`、GLM 请求携带 `thinking:{"type":"disabled"}`；开关经容器注入 Provider 构造函数，Provider 不读全局配置
  - 顺带修复真实体验缺陷：qwen3.5 默认思考导致首字延迟 30~40s（思考 token 被流式解析忽略，用户只看到等待）
- 运行过的验证：
  - uv run pytest → 86 passed（新增：配置默认/覆盖 1 例 + Ollama/GLM 请求体 think 断言 2 例）
  - 真实 Ollama 对比：think=false 0.54s vs think=true 2.30s（简单问题 4 倍，思考 144 token 只为答"5"）
  - 真实 GLM（glm-4.5-air）thinking=disabled 流式调用正常
  - 重启后端后 SSE 实测：整轮 RAG 回答（50 个 delta）13.3s 完成，对比此前仅首字 30~40s
- 运维教训：Windows 下 TaskStop 只杀 shell 不杀 uvicorn 子进程（孤儿进程占住 8000，表现为旧代码+对 Ollama 连接异常 500）；需 netstat 找 PID 后 taskkill/Stop-Process 强杀
- 额外发现并修复：backend/.env.example 一直被根 .gitignore 的 `.env.*` 模式误伤、从未真正入库（历次"已提供模板"的记录实际只存在于本地）；已加 `!.env.example` 否定规则并收录
- 提交记录：本轮提交
- 下一步最佳动作：可选增强（会话重命名/停止按钮/部署收敛），无阻塞项

### Session 014（FE-002 ~ FE-010 前端全部功能）
- 日期：2026-09-06
- 本轮目标：完成前端全部剩余功能（FE-002~010），直至前后端全链路可用
- 技术决策：
  - FE-002：types/api/state 三层（client.ts request<T>+ApiError 解析统一错误；chat.ts fetch 手动消费 SSE，EventSource 不支持 POST）；React Context 轻量状态，UI 组件零直接 fetch
  - FE-003：语义化主题 token（stone 暖灰 + 唯一 emerald 强调色，明暗双主题跟随系统）；圆角体系（控件 lg/气泡 2xl/徽标 full）；图标统一 @phosphor-icons/react（不手绘 SVG）
  - FE-004：新会话延迟创建（第一句提问时才 POST，title=提问截短 20 字，解决后端不自动改标题导致的列表不可辨认）；乐观插入 + SSE 增量写入
  - FE-006/008：删除统一两步确认交互；新增 danger 语义色 token
  - FE-007：streamingRef 守卫生成中禁止切换/新建会话（openConversation/startNewChat 入口拦截）
  - FE-010：助手消息 react-markdown 渲染（默认不解析原始 HTML）；ink-faint 对比度提升至 WCAG AA（明暗两套）
- 运行过的验证（全部真实执行）：
  - npm run build（tsc 类型检查 + vite）每个功能均通过；fetch 隔离机械校验（仅 api/ 层 3 处）
  - 真实浏览器（IAB）：Shell 布局/视图切换截图；提问→新会话以提问为标题→流式回答「二十年」引用专利法第四十二条→后端确认持久化
  - 增量渲染采样序列 506→681(生成中)→823(完成)；生成中点击其他会话被守卫阻止；停后端发送→502 错误条、重启恢复
  - 会话删除：条目消失 + 刷新不复活 + 删除当前会话回新对话
  - 知识库：真实 MD 文档经 input change 路径上传→201→embedding 入库「可检索」；bad.exe 前端预校验拒绝；两步确认删除
  - FE-009 联调双闭环：劳动法问答（引用新上传劳动合同法文档）→刷新恢复→删除；上传消保法→立即 RAG（三倍赔偿+五百元）→删除清理
  - 终验：后端 uv run pytest 83 passed；前端 build 通过；Markdown 渲染截图复验
- 已记录证据：feature_list.json FE-002~010 全部 passing（附各项验证细节）
- 提交记录：7f6a3b9、4009527、06e0168、2fcc092、10b0664、a531eb0、870f6b0、fd7a0bb、本轮收尾提交
- 已知风险或未解决问题：
  - Ollama qwen3.5:4b 首 token 延迟约 30~40s（本机 CPU 推理），回答期间 UI 有状态提示但体验依赖模型速度
  - 前端依赖较新（Vite 8/TS 7/React 19），生态兼容问题留意
  - 深色主题为 token 自动切换，未做浏览器强制暗色截图（结构同源，风险低）
- 下一步最佳动作：可选产品化增强（会话重命名、回答停止按钮、深色主题手动开关、部署收敛 CORS）

### Session 013（FE-001 前端项目基础框架）
- 日期：2026-09-06
- 本轮目标：FE-001 在 frontend/ 建立 React + TS + Vite + Tailwind + React Router 基础框架
- 技术决策：
  - 手写脚手架而非 create-vite 模板：文件全部带中文注释，结构与后续 FE 对齐（pages/api/components/types 预留目录 + .gitkeep）
  - Tailwind CSS v4（@tailwindcss/vite 插件 + 单行 @import），无 tailwind.config；dev 经 Vite 代理 /api → 127.0.0.1:8000，前端代码只用相对路径，规避开发期 CORS
  - build 脚本为 tsc --noEmit && vite build（类型检查前置）；React Router 用最直白的 BrowserRouter/Routes/Route 写法（0 基础友好）
  - 踩坑：TS7 对 CSS 副作用导入报 TS2882，补 Vite 标准 vite-env.d.ts 解决
- 运行过的验证：
  - npm install 成功（React 19.2 / Router 7.18 / Tailwind 4.3 / Vite 8.2 / TS 7.0，0 漏洞）
  - npm run build 通过（类型检查 + 152ms 打包）；dist CSS 含按需生成的 Tailwind 工具类
  - npm run dev 启动 292ms ready；curl / → 200 且 title/挂载点正确
  - 真实后端启动后 curl /api/health 经代理返回 {"status":"ok"}，后端访问日志确认 200
- 提交记录：本轮提交
- 下一步最佳动作：FE-002 前端 API 与状态基础层

### Session 012（前端 feature 清单评审与修订）
- 日期：2026-09-06
- 内容：前端开工前评审 feature_list.json FE-001~010 的适合性、准确性、全面性（逐条对照 PRODUCT.md、ARCHITECTURE.md 第 7 节 API 契约与后端实际路由/DTO）
  - 发现并修复真实缺口：PRODUCT.md 要求知识库管理"查看文档名称、删除文档"，FE-008 原定义只有上传与状态反馈 → 补入侧边栏切换入口、文档列表展示（名称/大小/状态）、文档删除；FE-009 联调闭环同步补"文档删除"
  - 精度修订：FE-001 锚定 frontend/ 目录；FE-002 明确类型定义范围（统一错误结构 {code,message}、SSE 事件）并锁定轻量状态管理（hooks/Context）
  - 其余 FE-003~007、FE-010 与 PRODUCT.md 及后端 SSE 协议（delta/done/error）逐条吻合，未改动
- 基线验证：uv run pytest → 83 passed；后端 9 个端点与 ARCHITECTURE.md 第 7 节一致；feature_list.json JSON 校验通过
- 提交记录：本轮提交

### Session 011（四层测试验证 + 文档与清单整合）
- 日期：2026-09-06
- 内容：
  - 四层测试全部真实验证通过：单元 37 / 集成 39 / 接口 7（自动化合计 83）+ 端到端真实链路（真实 uvicorn + 专利法上传入库 + 流式 RAG 问答引用第四十二条 + 持久化）
  - ARCHITECTURE.md 全面整合：530 行/30 节 → 238 行/10 节（删重复实现叙述，补端口清单、边界守护、四层测试体系、扩展点）
  - feature_list.json 后端 11 项 description/evidence 同步至演进后事实；并做过 62 项声明的机械审计（62/62 通过），审计脚本按用户决定删除（f46352c）
  - qa_workflow.py 加 @runtime_checkable 与装配守卫测试
- 提交记录：48f5596、21ca7ef、15ad5f5、b3bb4bc、f46352c

### Session 010（DDD 合规整改 + agent OOP + langgraph 隔离）
- 日期：2026-09-06
- 内容：
  - AST 机械扫描发现并修复 3 处违例：Database 端口迁至 domain/repositories/database.py；新增 QaWorkflow 领域端口（QaWorkflow Protocol，ChatService 解除 langgraph 依赖）；application 对 infrastructure 的反向导入清零
  - app/agent/ 确立为 langgraph 唯一隔离区：create_qa_workflow 工厂唯一入口 + OOP 重构（AgentNode 命令模式/QaGraphBuilder 建造者/LangGraphQaWorkflow 适配器）
  - 新增 tests/unit/test_ddd_boundaries.py（4 项 AST 边界守护随 pytest 运行）
  - ARCHITECTURE.md 同步端口清单、隔离区规则、OOP 结构
- 提交记录：f9c2cb5、9bf599a、675ec72、46f391b
- 测试状态：全量 83 passed（unit 37 + integration 46）

### 补记（Session 007 之后、008 之前的一轮，未及时登记）
- 提交 5b375bf：BE-010 GLM 真实调用补验通过（glm-4.5-air）；BE-012 用真实《专利法》TXT+MD 复验并修复定长切分截断法条的缺陷（chunk_text 改段落感知）；修复相对路径随启动目录漂移（settings 锚定 resolved_*）；停止跟踪运行时数据（data/、backend/data/）；收录用户改动（md 格式支持、tests/data_source 测试数据）

### Session 009
- 日期：2026-09-06
- 本轮目标：所有 LLM 问答统一走 LangGraph 图（应用户要求）
- 技术决策：generate 节点内经 get_stream_writer() 推送 token；非流式 ainvoke、流式 astream(stream_mode=custom) 执行同一节点；ChatService 精简为（会话服务 + 图），不再直接依赖 RAG/LLM——检索与 Prompt 组装只在图内一份实现
- 运行过的验证：全量 pytest 77 passed（新增 2 个 astream custom 用例）；真实服务器 E2E：专利法提问 SSE 55 个 delta 经图产出，回答引用第四十二条，消息持久化正常
- 提交记录：本轮提交

### Session 008
- 日期：2026-09-06
- 本轮目标：后端全面检查 + 测试分层重组 + 完整测试
- 已完成：
  - 移除空占位包（agent/nodes、agent/tools、application/dto）；清理测试未用导入
  - 测试分层：tests/unit/（33 个，纯逻辑无外部 IO）+ tests/integration/（42 个，真实 SQLite/Chroma/Mock/完整应用）
  - pyproject 增加 pytest testpaths；ChatService.send_message 保留（非流式入口，LangGraph 图唯一运行时消费者，暂无路由调用）
- 运行过的验证：unit 33 + integration 42 = 75 passed；启动 smoke 通过
- 提交记录：4be634b

### Session 007
- 日期：2026-09-06
- 本轮目标：完成后端全部剩余功能（BE-014 ~ BE-022）
- 技术决策：
  - BE-014：RagService + build_context（含来源标注，空结果返回空串衔接"信息不足"策略）；新增 min_score 相似度阈值。
  - BE-015/016：LangGraph StateGraph（START→retrieve?→generate→END），Agent 仅依赖 LLMProvider 抽象；Prompt 组装集中于 agent/prompts.py。
  - BE-017：LEGAL_SYSTEM_PROMPT 三条硬规则（依据知识库并注明来源/无依据明确声明/严禁虚构法条）。
  - BE-018：ConversationService 统一会话业务（缺失会话统一异常，级联删除）。
  - BE-019~021：API 全异步、路由只调 Service、统一错误结构 {code,message}；ChatService 流式"完成才持久化"；DocumentService 状态机 processing→ready/failed。
  - 修复的真实缺陷：日志 extra 误用 LogRecord 保留字段（message/filename）使业务 404 变 500；API 测试改在 LOG_LEVEL=INFO 下运行以覆盖此类问题。
- 已完成：RAG 检索、LangGraph 双工作流、回答策略、对话服务、全部 REST/SSE API、统一异常体系
- 运行过的验证：
  - `uv run pytest tests -q` → 75 passed 全量通过
  - 真实 RAG 端到端（nomic-embed-text + Chroma + qwen3.5:4b）：有依据答"试用期不超过六个月"并引用来源；无关问题明确声明信息不足
  - 真实 uvicorn：会话创建/40401 统一结构/TXT 上传入库 ready/bad.exe 40001 全部正确
- 已记录证据：feature_list.json BE-014~022 evidence
- 提交记录：7d472e0 (BE-014)、2289115 (BE-015/016/017)、d1ab058 (BE-018)、e0eb5e7 (BE-019~022)
- 已知风险或未解决问题：BE-010 GLM 真实调用待密钥；前端（FE-001~010）未开始
- 下一步最佳动作：前端 FE-001 前端项目基础框架；或提供 GLM_API_KEY 后补验 BE-010

### Session 005
- 日期：2026-09-06
- 本轮目标：BE-009 ~ BE-013（用户指定"完成 5 个 feature"）
- 技术决策：
  - BE-009：LLMProvider 抽象（chat 同步 + stream 异步生成器 + model_name）；ChatMessage 复用 MessageRole。
  - BE-010：Ollama（NDJSON 流）与 GLM（OpenAI 兼容 + SSE 流）实现；Provider 构造函数支持 httpx transport 注入作为测试接缝；glm 缺密钥时装配即报错。
  - BE-011：解析器策略接口（domain/services）+ Pipeline 编排（application），解析经 to_thread；TextParser 多编码回退（utf-8/gb18030/big5）。
  - BE-012：PdfParser（pypdf 逐页提取）；损坏 PDF 与无文本层 PDF 均明确报错；测试用 fpdf2 生成真实 PDF。
  - BE-013：EmbeddingService 抽象 + OllamaEmbeddingService（/api/embed 批量）+ KnowledgeIngestionService 入库编排；新增 OLLAMA_EMBEDDING_MODEL 配置。
  - 教训：uv pip install 进 venv 的包必须同步写入 pyproject，否则 uv sync 会将其移除（pypdf 曾被剥离，已修复）。
- 已完成：LLM 抽象与双实现、文档 Pipeline、PDF/TXT 解析、Embedding 与入库编排、容器装配齐备
- 运行过的验证：
  - `uv run pytest tests -q` → 53 passed 全量通过
  - Ollama 真实调用：chat 与流式问答通过（qwen3.5:9b，经 OLLAMA_MODEL 覆盖；scripts/verify_ollama_stream.py）
  - 知识库入库端到端：真实 Chroma + 确定性 embedding，检索命中带 metadata 的 chunk、按 document_id 删除
  - 真实启动：Database/VectorStore 初始化日志正常，curl /api/health → ok
- 已记录证据：feature_list.json BE-009/011/012 = passing；BE-010/BE-013 = in_progress（环境阻塞见下）
- 提交记录：41aed90 (BE-009)、2de5486 (BE-010)、075a736 (BE-011)、8b393bf+9def484 (BE-012)、e395422 (BE-013)
- 已知风险或未解决问题：
  - BE-010 剩余：GLM 真实调用需配置 GLM_API_KEY 后补验
  - BE-013 已补验通过（Session 006）：真实 nomic-embed-text 向量端到端入库检索成功；此前"模型不存在/服务不支持 embeddings"的判断有误——第一次查 /api/tags 时输出被截断导致漏判，且当时服务状态不同；教训：结论前必须完整读取输出
- 下一步最佳动作：BE-014 RAG 检索服务

### Session 006
- 日期：2026-09-06
- 本轮目标：应用户要求将全项目 embedding 模型改为 nomic-embed-text:latest，并核实模型可用性
- 技术决策：对话模型 OLLAMA_MODEL 保持 qwen3.5:4b 不变，仅改 OLLAMA_EMBEDDING_MODEL
- 已完成：settings.py 与 .env.example 更新；BE-013 真实向量端到端补验；新增 scripts/verify_real_embedding.py
- 运行过的验证：pytest 53 passed；真实链路 DocumentPipeline→OllamaEmbedding(nomic-embed-text, 768 维)→Chroma，语义检索命中（score 0.6207）
- 提交记录：5e27b76（配置）、本轮 BE-013 置 passing 提交
- 下一步最佳动作：BE-014 RAG 检索服务

### Session 004
- 日期：2026-09-06
- 本轮目标：BE-006 / BE-007 / BE-008（用户指定"完成 3 个 feature"，中途因会话中断恢复续做）
- 技术决策：
  - BE-006：DocumentChunk/RetrievedChunk 数据契约；VectorStore 抽象含 initialize/close 生命周期；embedding 由调用方传入，向量库与 embedding 模型彻底解耦。
  - BE-007：chromadb PersistentClient + law_chunks 集合（cosine 空间，score=1-distance）；所有阻塞调用经 asyncio.to_thread 包装；不使用内置 embedding 函数。
  - BE-008：MilvusVectorStore 骨架调用即抛明确 NotImplementedError（拒绝静默空结果）；容器工厂按 VECTOR_STORE_PROVIDER 分支，向量库初始化接入 lifespan。
- 已完成：VectorStore 抽象与契约测试、Chroma 实现、Milvus 骨架、容器工厂与 lifespan 接入
- 运行过的验证：
  - `uv run pytest tests -q` → 28 passed（Chroma 4：写入检索/删除隔离/跨连接持久化/幂等；工厂 3：chroma 解析/milvus 解析/明确报错）
  - 真实启动：日志 "VectorStore initialized (provider: chroma)"，curl /api/health → ok
  - VECTOR_STORE_PROVIDER=milvus 时 initialize 抛出明确 NotImplementedError（早暴露设计生效）
- 已记录证据：feature_list.json BE-006/BE-007/BE-008 evidence
- 提交记录：7d96fe8 (BE-006)、9aa3ece (BE-007)、664d8f4 (BE-008)
- 已知风险或未解决问题：chroma 依赖较重（安装体积大），启动耗时略有增加；其余无
- 下一步最佳动作：BE-009 LLM Provider 抽象层（Ollama/GLM 前置）

### Session 003
- 日期：2026-09-06
- 本轮目标：BE-003 / BE-004 / BE-005（用户指定"完成 3 个 feature"）
- 技术决策：
  - BE-003：自研轻量 DIContainer（接口注册工厂+单例），不引入 DI 框架；containers.py 为唯一装配点，挂载到 app.state.container。
  - BE-004：领域实体用纯 dataclass（零技术依赖）；Repository 接口在 domain 层；Database 抽象含 transaction() 事务上下文。
  - BE-005：aiosqlite 实现；提交边界由 Database 层统一控制（_tx_depth 计数），仓库不自行 commit——测试暴露了"仓库自动提交破坏外层事务回滚"的真实缺陷后修正。
  - 本机环境备注：Ollama 已运行（本机现装有 qwen3.5:9b）；Ollama 默认模型配置已于后续提交改为 qwen3.5:4b（BE-010 验证前需确认该模型已拉取）；GLM_API_KEY 未设置。
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
