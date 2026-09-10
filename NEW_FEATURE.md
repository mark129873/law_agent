# NEW_FEATURE.md -- 本轮新增功能（待同步到 PRODUCT.md 与 feature_list.json）

## BE-024 数据库实现迁移到 SQLAlchemy async，并将列表排序职责上移到应用层

### 做了什么
1. **数据库实现从「手写 SQL + aiosqlite」替换为 SQLAlchemy 2.0 async Core**：
   - 新增 `backend/app/infrastructure/database/sqlalchemy/`（`schema.py` 表结构元数据、`types.py` 时区无损时间列、`database.py` Database 端口实现与三个仓储）。
   - 删除原 `backend/app/infrastructure/database/sqlite/database.py` 与已无用的 `mysql/` 空占位包（保留 SQLite 作为默认 Provider，只是改用 SQLAlchemy 访问）。
   - `aiosqlite` **保留为依赖**：它从"业务实现直接使用的驱动"降级为"SQLAlchemy 的 SQLite 异步驱动"（`sqlite+aiosqlite:///...`），业务代码不再直接导入它。
   - 表结构保持与既有数据库文件兼容：三张表（conversations / messages / documents）+ `messages.conversation_id` 索引 + `sources` 列；旧库启动时仍幂等补 `sources` 列。
2. **外键改为表级约束**：`messages.conversation_id → conversations.id ON DELETE CASCADE`，由 SQLAlchemy `ForeignKey(ondelete="CASCADE")` 生成表级 `FOREIGN KEY` 子句（列内联 `REFERENCES` 在 MySQL 上会被忽略，这是接入 MySQL 8.0 的必要前置修复）。
3. **时间列时区无损**：自定义 `IsoDateTime` 类型装饰器，以 ISO-8601 字符串（`VARCHAR(32)`/`TEXT`）读写，读回仍是带 `tzinfo` 的 `datetime`，与旧实现逐字节一致（SQLAlchemy 默认 `DateTime` 会丢时区，会使"时间戳必须保留时区"的既有断言失败）。
4. **排序职责上移到应用层，且只按时间判断**：
   - 仓储 SQL 不再出现 `ORDER BY`（原 `ORDER BY created_at ASC, rowid ASC` 中的 `rowid` 是 SQLite 专有语法，MySQL 没有）。
   - 应用服务负责排序：会话列表按 `created_at` 正序（最早在上）、会话消息按 `created_at` 正序（对话顺序）、文档列表按 `created_at` 倒序（最新在上）。
   - 同一时刻（`created_at` 完全相同）的记录不再有第二排序键，顺序由底层返回顺序决定，Python `sorted` 稳定排序保证同一份数据多次查询结果一致。

### 为什么这么做
- 架构第 10 节原本预留「新增 `infrastructure/database/mysql/` 实现」：那意味着两套手写 SQL 各自演化，极易出现「SQLite 测试全绿、MySQL 行为不同」的方言漂移。改用 SQLAlchemy Core 后，表结构、约束、DML 全部方言无关，MySQL 接入只剩「换 URL + 装异步驱动」。
- 排序属于业务展示规则（FE-012 的"旧在上新在下"是产品要求），不属于存储职责。放进应用层后，同一份排序规则对任何存储实现都成立，仓储回归纯粹的 CRUD 契约；这也修掉了内存 Fake（倒序）与 SQLite 实现（正序）此前的排序不一致。
- 只按时间排序是产品口径：排序依据唯一且可解释，不再依赖 SQLite 的物理行号。

### 验收标准
- 全量 `uv run pytest` 通过（本轮基线 92 个，迁移后数量只增不减）。
- 与旧实现同一套行为断言在 SQLAlchemy 实现上全绿：跨连接持久化、外键级联删除、真实事务回滚、建表幂等、旧库 `sources` 列迁移与数据保留、`sources` JSON 往返。
- 新增排序验证：**乱序写入（先写入时间较晚、后写入时间较早）后，服务层按时间正序/倒序返回**；同时间和多次查询结果稳定。
- 时间列读回保留 `tzinfo`。
- `tests/unit/test_ddd_boundaries.py` 通过：sqlalchemy 只出现在 infrastructure 层。
- 真实启动路径可用：`uv run uvicorn app.main:app` 自动建库，`curl /api/health` 返回 ok；`scripts/verify_real_e2e.py`（依赖本机 Ollama）可选执行。

### 用户可见影响
无行为变化：会话列表仍是「旧在上新在下」、对话内消息仍是提问在前回答在后、知识库文档列表仍是最新上传在最前。

### 实测结果（本轮真实验证）
- `uv run pytest`：**98 passed**（迁移前基线 92，新增 6 个：事务提交/先读后事务/排序契约 4 例等），无失败无跳过。
- 旧库兼容实测：用**迁移前版本创建的** `backend/data/law_agent.db`（4 条会话、4 个文档、含 `sources` 来源内容）直接启动新实现——`uv run uvicorn app.main:app` 启动正常、`/api/health` 返回 ok；`GET /api/conversations` 返回创建时间正序、`GET /api/documents` 返回上传时间倒序，中文标题/文件名与 `sources` JSON 完整无乱码、时间戳带 `+00:00`。
- 写路径实测：在该旧库上 `POST /api/conversations` → 201（4→5 条），`DELETE` → 204（回到 4 条），会话已清理；结构化 JSON 日志（`Database initialized`、`Conversation created/deleted`）正常输出。
- 新库迁移路径：`test_schema_migration_adds_sources_column` 用同步引擎构造 FE-023 之前的旧表 + 历史数据，验证 `init_schema` 幂等补列、数据保留、迁移后可写入带来源消息、重复调用不报错。
- 顺带修复：`feature_list.json` 缺失逗号导致文件整体无法被 JSON 解析（FE-012 条目处），已修复并校验可解析。

