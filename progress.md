# progress.md -- 会话进度日志

## 当前已验证状态
- 仓库根目录：`C:\Users\nnnnnn\Desktop\law_agent`
- 标准启动路径：`cd backend && uv sync && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 标准验证路径：`cd backend && uv run pytest tests -q`；启动后 `curl http://127.0.0.1:8000/api/health`
- 当前最高优先级未完成功能：无（后端 BE-001~022 与前端 FE-001~010 全部 passing，32 项功能全部完成；全项目五层测试轮已通过）
- 当前 blocker：无

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
