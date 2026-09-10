# NEW_FEATURE.md -- 本轮新增功能（待同步到 PRODUCT.md 与 feature_list.json）

> 上一轮（BE-024：迁移到 SQLAlchemy Core + 排序上移应用层）的功能说明与实测结果已归档在
> `feature_list.json`（BE-024 evidence）与 `progress.md`（Session 020），本文件只保留本轮内容。

## BE-025 数据库访问从 SQLAlchemy Core 改造成 SQLAlchemy ORM（最小代价路径）

### 做了什么
1. **表结构改为声明式 ORM 模型**：新增 `backend/app/infrastructure/database/sqlalchemy/models.py`
   （`DeclarativeBase` + `ConversationModel` / `MessageModel` / `DocumentModel`），
   取代原 Core 的 `schema.py`（已删除）。表名、列名、类型、索引、外键级联与 BE-024 完全一致。
2. **新增显式的领域实体 ↔ ORM 模型映射层**：`mappers.py` 提供 `to_domain_*` / `to_model_*`。
   领域层保持纯 dataclass（DDD 边界守护测试禁止 domain 导入 sqlalchemy），
   因此 ORM 模型**只能**住在 infrastructure，两个模型体系之间必须有一层映射——
   这层映射用 Data Mapper 模式固定下来，不再散落在各仓储方法里。
3. **会话（Session）取代裸连接**：`SQLAlchemyDatabase` 改用 `async_sessionmaker` + 单个
   `AsyncSession`（与 BE-024 的单连接策略等价，不引入连接池——池化需要改端口形状，属独立改造）。
   关键配置：`expire_on_commit=False`（否则 commit 后访问属性在异步上下文抛 `MissingGreenlet`）。
4. **仓储改为 ORM 写法**：`session.add()` + 事务栈守卫提交边界；`session.get()` 按主键取用；
   文档状态更新改为"取出模型→改属性"（保持 identity map 与数据库一致）；
   消息按会话删除保留批量 `delete()`（需要影响行数、避免 N+1 加载），
   并显式使用 `synchronize_session="fetch"` 让 session 与数据库同步，避免脏读。
5. **不使用 ORM 关系（relationship）**：本项目没有聚合内导航需求（消息永远按
   `conversation_id` 显式查询），因此不定义 relationship，也就没有异步懒加载（`MissingGreenlet`）
   这一整类风险；级联删除仍由表级外键 `ON DELETE CASCADE` 保证。
6. **领域实体永不出界**：仓储出口一律返回领域 dataclass，ORM 模型不越过 infrastructure
   边界（新增测试机械校验这一点），否则应用层会被 ORM 类型悄悄污染。

### 为什么这么做（在已知代价前提下的取舍）
- ORM 的真实收益（关系图、工作单元、自动脏检查、Alembic autogenerate 闭环）在本项目当前
  规模下几乎用不到，成本（多一层映射、session 状态语义、异步坑）却是实付的。
  本轮是**按用户决策落地**，因此采用最小代价路径：不动领域层、不动端口、
  不动应用服务层（排序仍在应用层按 created_at 判断），只替换 infrastructure 内部实现。
- 保留的"ORM 语言一致性"收益：表结构即 Python 类、字段改动有类型提示、后续引入 Alembic
  autogenerate 时模型即 schema 唯一真相。

### 验收标准
- 全量 `uv run pytest` 通过（本轮基线 98 个，数量只增不减）。
- BE-024 的全部既有行为断言在新实现上全绿：跨连接持久化、外键级联删除、事务提交/回滚、
  先读后开事务、建表幂等、旧库 `sources` 列迁移与数据保留、`sources` JSON 往返、时间保留时区。
- 新增 ORM 特有契约测试：提交后属性可安全读取（不抛 `MissingGreenlet`）、
  identity map 下"更新后回读"一致、批量删除后无脏读、仓储出口是领域实体而非 ORM 模型。
- 真实启动路径可用（`uv run uvicorn app.main:app`），且能用 BE-024 之前版本创建的旧库直接读写。

### 用户可见影响
无。API 契约、SSE 协议、排序行为、`sources` 存储格式全部不变。

### 实测结果（本轮真实验证）
- `uv run pytest`：**104 passed**（本轮基线 98，新增 ORM 契约测试 6 例）。
- ORM 特有契约测试（`tests/integration/test_orm_contract.py`，6 例全绿）：
  仓储出口是领域实体而非 ORM 模型（类型与模块双重断言）、
  `expire_on_commit=False` 下提交后仍可安全读属性（否则异步访问过期属性会抛 `MissingGreenlet`）、
  文档状态"改属性更新"后同一会话内回读不是过期值、
  批量删除后 session 内无残留（`synchronize_session="fetch"` 生效）、
  事务回滚能撤销属性级更新、整个数据库实例持有唯一会话。
- BE-024 的全部行为断言在新实现上原样通过（跨连接持久化/外键级联/事务提交与回滚/先读后事务/
  建表幂等/旧库补列迁移/来源 JSON 往返/时间保留时区/乱序落库仍按时间排序）。
- 旧库兼容实测：用**迁移前版本创建的** `backend/data/law_agent.db` 走标准启动路径
  `uv run uvicorn app.main:app` → `/api/health` ok；`GET /api/conversations` 4 条按 `created_at` 正序、
  `GET /api/documents` 4 条按上传时间倒序、`GET .../messages` 首条会话角色为 user → assistant；
  `POST /api/conversations` 201（4→5）→ `DELETE` 204（回到 4，测试会话已清理）。
- 旧库零破坏复核（只读 PRAGMA/sqlite_master 检查）：三张表未变、`messages` 仍含 `sources` 列、
  外键仍为 `conversation_id → conversations.id ON DELETE CASCADE`、索引 `idx_messages_conversation` 仍在、
  行数与验证前一致（4 会话 / 8 消息 / 4 文档）——ORM 的 `create_all` 对已存在表零改动。

