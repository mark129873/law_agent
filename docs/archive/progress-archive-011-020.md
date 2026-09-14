# progress 归档分卷 011-020（冷数据，只读）

> 本卷为冷数据：历史会话日志，沉降后不再修改。当前进度见仓库根 progress.md（热层）。
> 沉降规则见 AGENTS.md：Session 数 > 15 触发，每批固定沉降 10 个，文件名标注起止 Session 序号。

### Session 011（四层测试验证 + 文档与清单整合）
- 日期：2026-09-06
- 内容：
  - 四层测试全部真实验证通过：单元 37 / 集成 39 / 接口 7（自动化合计 83）+ 端到端真实链路（真实 uvicorn + 专利法上传入库 + 流式 RAG 问答引用第四十二条 + 持久化）
  - ARCHITECTURE.md 全面整合：530 行/30 节 → 238 行/10 节（删重复实现叙述，补端口清单、边界守护、四层测试体系、扩展点）
  - feature_list.json 后端 11 项 description/evidence 同步至演进后事实；并做过 62 项声明的机械审计（62/62 通过），审计脚本按用户决定删除（f46352c）
  - qa_workflow.py 加 @runtime_checkable 与装配守卫测试
- 提交记录：48f5596、21ca7ef、15ad5f5、b3bb4bc、f46352c

### Session 012（前端 feature 清单评审与修订）
- 日期：2026-09-06
- 内容：前端开工前评审 feature_list.json FE-001~010 的适合性、准确性、全面性（逐条对照 PRODUCT.md、ARCHITECTURE.md 第 7 节 API 契约与后端实际路由/DTO）
  - 发现并修复真实缺口：PRODUCT.md 要求知识库管理"查看文档名称、删除文档"，FE-008 原定义只有上传与状态反馈 → 补入侧边栏切换入口、文档列表展示（名称/大小/状态）、文档删除；FE-009 联调闭环同步补"文档删除"
  - 精度修订：FE-001 锚定 frontend/ 目录；FE-002 明确类型定义范围（统一错误结构 {code,message}、SSE 事件）并锁定轻量状态管理（hooks/Context）
  - 其余 FE-003~007、FE-010 与 PRODUCT.md 及后端 SSE 协议（delta/done/error）逐条吻合，未改动
- 基线验证：uv run pytest → 83 passed；后端 9 个端点与 ARCHITECTURE.md 第 7 节一致；feature_list.json JSON 校验通过
- 提交记录：本轮提交

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
