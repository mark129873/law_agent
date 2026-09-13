# 会话交接

## 当前已验证
- 现在明确可用的部分：
  - **Agent 模块一期重写全部完成（BE-032~041 + FE-014/015 + BE-040 passing；BE-030 deprecated）**：主图 15 节点（意图路由→编排循环→Capability 分派→观察→回答收尾链）+ Local Legal RAG 子图 10 节点（检索规划→策略 fan-out→三查询变体→并发混合检索→重排→评估→恢复循环→结果）+ Web/Plugin Stub + 服务层（LLMService 结构化输出容错 / MilvusService 端口适配 / RerankerService / CitationService）。
  - **前端**：检索策略面板（plan 事件全量查询）+ 节点状态浅色过程行（status 事件，done 后保留、新提问清空）；FE-001~015 全部 passing。
  - **测试体系**：自动化 197 个（unit 127 含 agent 76 / integration 70 含 agent 12 / api 9）；test_milvus_vector_store.py 5 例需真实 Milvus（不可达自动跳过），其余封闭。Fake 体系：脚本化 LLMProvider（系统提示特征分流）+ Fake Embedding/VectorStore/RerankScorer。
  - **架构文档**：docs/adr/0001~0008（八项决策）+ docs/glossary.md 术语表 + ARCHITECTURE §5 全重写（主图/子图拓扑、事件机制、双规则）+ docs/qa_graph.mmd（15 节点，export_qa_graph.py 可重导出）。
- 最近一轮实际跑过的验证（2026-09-13，Session 031 收尾）：
  - 干净环境（删 data + reset_milvus.py）全量 `uv run pytest tests -q` → **197 passed**
  - 真实 E2E（verify_real_e2e.py，GLM glm-4.5-air + 真实 Milvus + RERANK_ENABLED=false）：上传 TXT/MD 201 ready → plan 携带检索策略 → 15 节点 status 贯通（含子图）→ 回答正确引用第四十二条"二十年"+【来源】→ sources 持久化一致 → 事件序 plan<sources<delta
  - 浏览器实操（IAB 1280x800）：法律问题浅色状态行实时滚动（正在检索知识库…）+「检索策略（1 条查询）」→ done 后状态保留 +「参考文档 10」；第二个法律问题一次成功引用第七十一条赔偿规则+来源标注；闲聊直接回答（无检索策略/无"暂无依据"声明/仅主图节点状态）；grounding 双打回→兜底谨慎回答路径真实触发
  - 前端 npm run build（tsc + vite）通过；验证后 law_chunks/data/前后端进程已清理

## 本轮改动（Session 031：一期 Agent 重写，13 个功能 12 次提交）
- **后端 agent 模块整体重写**：目录 nodes//prompts//services//subgraphs/legal_rag//web//plugins//utils/ + graph.py/state.py/config.py/schemas.py/constants.py/events.py/node_status.py；旧四文件先搬迁 _legacy/（规避同名包冲突）后于 BE-038 删除
- **关键机制**：
  - 事件：QaStreamEvent 增 status 类型；emit_event=ContextVar 注入队列（**langgraph 1.2.11 子图 custom 事件不上浮父图的实测缺陷的规避**，ADR-0008）；LangGraphQaWorkflow.astream=ainvoke+队列排空，GeneratorExit 取消任务
  - 节点包装：with_node_status 统一起止 status+日志（异常也推 end）；RAG 复合节点显式 I/O 过滤（_RAG_OUTPUT_KEYS 四键回写）
  - RAG 子图：strategy_router 条件边 fan-out 多选策略（列表通道 operator.add 归约防并发写冲突）；hybrid_retriever 汇总查询（去重/排除已检索/≤8）+asyncio.gather 并发+单查询重试 1 次；evidence_ranking 三级键去重+RRF 预截断 20+original_query 统一 rerank；恢复循环受 max_retries=2（route_after_evidence_grade 条件边检查）
  - 主图：orchestrator 预算双保险（超限强制 finish）；grounding 规则档+LLM judge 双档，每次执行 +1 步数（防打回回路绕过预算）；direct 路径跳过检索直接流式；finish 路径 answer_generator 唯一流式出口（direct 草稿透传）；Web/Plugin 仅 NOT_IMPLEMENTED/DISABLED
- **配置新增**：RERANK_ENABLED（默认 true；本机 .env 置 false——CPU 无 CUDA 实测 15s/对不可行）、RERANKER_MODEL_PATH（本机指向本地快照）、RERANKER_DEVICE、rerank_max_candidates=20（粗排→精排预截断）
- **前端**：types/chat.ts/AppContext/MessageBlock/ChatPage 适配 status 事件与检索策略文案（「问题拆解」→「检索策略（N 条查询）」）
- **测试**：删旧 test_agent_graph(19)+test_agent_parsing(13)；新增 tests/{unit,integration}/agent/ 88 例；test_api ScriptedLLM 改标记分流；test_ddd_boundaries 加 sentence_transformers/torch 隔离（现 5 例）
- **文档**：ARCHITECTURE §0/§1/§2/§3/§4/§5/§6/§7/§9/§10 重写同步；PRODUCT.md §3/§4 行为变更（先于代码）；RELIABILITY agent 埋点说明；ADR-0001~0008；glossary.md

## 仍损坏或未验证
- 已知缺陷：无
- 未验证路径：
  - Ollama LLM 路径的真实模型 E2E（本轮走 GLM 配置；图闭环行为由集成测试锁定）
  - rerank 精排的真实质量评估（本机 CPU 不可行已关；功能本体已由一轮真实 rerank + 单测锁定，GPU 机器 RERANK_ENABLED=true + RERANKER_DEVICE=cuda 即启用）
  - MySQL 8.0 真实接入、连接池化（沿袭既有未验证项）
  - Web Search 二期（替换 web_search_stub_node 即可，suggested_external_queries 已透传主图 state 备用）
- 下一轮会话需要注意的风险：
  - **每问题 LLM 调用 5~8 次**（忠实设计 D3）：本地 Ollama 部署延迟明显，建议 PLANNER_PROVIDER=glm；OllamaProvider 仍无重试（历史遗留，调用次数变多后风险放大）
  - **grounding judge 模型方差**：GLM 偶发首答缺【来源：被规则档打回（重生成/兜底已验证兜住）；judge 用主模型，本地小模型判分质量未评估（解析失败安全放行）
  - **rerank 降级态可观测**：RERANK_ENABLED=false 时 evidence_ranking trace 带 reranker_degraded=true；改 Prompt 输出格式必须同步 grounding 规则档的【来源：/信息不足声明字面锚点
  - **LangGraph 陷阱（延续有效）**：同一节点静态出边与条件边不能并存（InvalidUpdateError）；并行写通道必须配 operator.add 归约器；条件回边必须自带预算检查
  - **子图事件不上浮**：langgraph 升级后若修复该缺陷，可评估回归原生 custom 流（当前 ContextVar 机制工作良好，无必要）
  - **启动前置**：Milvus 必须可达（docker start milvus-etcd milvus-minio milvus-standalone）；pymilvus import 的 load_dotenv 副作用依旧（敏感配置测试已 delenv 防御）
  - **测试干净环境流程**：删 `backend/data/` + `uv run python scripts/reset_milvus.py`（两步都要）
- 下一步最佳动作（需用户决定）：可选产品增强（会话重命名/停止按钮/CORS 收敛）；MySQL 8.0 接入；Web Search 二期立项
- 这一步中哪些东西不要动：后端 API 契约（§7 SSE 协议——status 为向后兼容扩展）；统一错误结构 {code,message}；前端 api/state 分层；messages.sources 存储格式；领域层零技术依赖（pymilvus/langgraph/sentence_transformers 不得进 domain，守护测试会拦）；langgraph 与重型推理库只允许 app/agent/ 导入；**Milvus 集合 schema 与 Strong 一致性**；**RRFRanker k=60 口径**；**双预算常量（max_global_steps=4 / max_retries=2 / rerank_max_candidates=20）**（防死循环与可行性边界，调整属行为变更需走测试）；**BE-017 字面锚点（【来源：/知识库中暂无相关依据）**与 grounding 规则档、answer Prompt 三方联动

## 命令
- Milvus 启动：`cd backend && docker compose up -d`（容器名冲突时：`docker start milvus-etcd milvus-minio milvus-standalone`）
- 后端启动：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 干净环境重置（RELIABILITY.md，两步）：删除 `backend/data/` + `uv run python scripts/reset_milvus.py`
- 后端验证：`cd backend && uv run pytest tests -q`（全量 197 个；Milvus 未启动时 5 例自动跳过）
- 数据落点确认：SQLite `backend/data/law_agent.db`；Milvus 集合 `law_chunks`（容器卷）
- 前端构建/启动：`cd frontend && npm install && npm run build` / `npm run dev`
- 端到端（需 Milvus + GLM/Ollama）：启动服务器后 `PYTHONPATH=backend python backend/scripts/verify_real_e2e.py`
- 图导出：`cd backend && uv run python scripts/export_qa_graph.py`（写入 docs/qa_graph.mmd，--png 可选）
- 定向调试：`LOG_LEVEL=INFO uv run uvicorn app.main:app --port 8000`；OpenAPI http://127.0.0.1:8000/docs
