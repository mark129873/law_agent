# progress.md -- 会话进度日志

## 当前已验证状态
- 仓库根目录：`C:\Users\nnnnnn\Desktop\law_agent`
- 标准启动路径：`cd backend && uv sync && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 标准验证路径：`cd backend && uv run pytest tests -q`；启动后 `curl http://127.0.0.1:8000/api/health`
- 当前最高优先级未完成功能：前端 FE-001（后端 BE 全部 22 项 passing，四层测试全部验证通过；前端 FE-001~010 清单已于本轮评审修订确认，可作为开发依据）
- 当前 blocker：无

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
