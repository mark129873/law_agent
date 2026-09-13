# progress.md -- 会话进度日志

## 当前已验证状态
- 仓库根目录：`C:\Users\nnnnnn\Desktop\law_agent`（当前分支 feature/auto_coder）
- 标准启动路径：`cd backend && docker start milvus-etcd milvus-minio milvus-standalone && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 标准验证路径：`cd backend && uv run pytest tests -q`（全量 197 个自动化测试，真实 Milvus 集成测试在服务不可达时跳过）；启动后 `curl http://127.0.0.1:8000/api/health`
- Agent 模块一期重写（BE-032~041 + FE-014/015 + BE-040）全部 passing：主图 + Local Legal RAG 子图 + Web/Plugin Stub + 服务层 + 节点状态流式展示，架构决策见 docs/adr/0001~0008，术语表 docs/glossary.md
- 已知性能边界：本机 CPU（无 CUDA）上 Qwen3-Reranker-0.6B 约 15s/对，本地部署默认 `RERANK_ENABLED=false` 走 RRF 降级序（GPU 机器可开启精排）
- 当前最高优先级未完成功能：无——BE-001~041 与 FE-001~015 全部 passing 或 deprecated（BE-007/008/028/030 deprecated）
- 当前 blocker：无
- 冷数据归档：docs/archive/progress-archive-001-010.md、progress-archive-011-020.md（Session 001~020 历史记录；沉降规则：Session > 15 触发，每批沉 10 个，起止序号命名）


### Session 031（一期 Agent 模块重写：BE-032~041 + FE-014/015 + BE-040 全部落地）
- 日期：2026-09-13
- 本轮目标：按 legal_agent_phase1_technical_design.md 对 agent 模块整体重写（主图 + 独立 Local Legal RAG 子图 + Web/Plugin Stub + 服务层），并按用户决策 D1~D5 实现检索策略全量展示、直接回答路径、节点状态流式展示（Codex 风格浅色小字）、rerank top-10
- 技术决策（详见 plan.md 与 docs/adr/0001~0008）：
  - 主图 15 节点（意图路由/编排/动作路由/RAG 子图/Web+Plugin Stub/观察/直接回答/回答生成/grounding/兜底/收尾）+ 子图 10 节点（检索规划/策略路由/三查询变体/并发混合检索/证据重排/评估/恢复规划/结果）；预算 max_global_steps=4 与 max_retries=2 相互独立（ADR-0007）
  - 服务层适配领域端口：MilvusService→VectorStore（不直连 SDK）、LLMService 结构化输出=JSON 容错+重试 1 次+安全默认、RerankerService=CrossEncoderScorer 懒加载+失败降级（ADR-0003/0004）
  - **重大实测发现：langgraph 1.2.11 子图节点 custom 事件不上浮父图 astream**（探针证实）→ 事件机制改为 ContextVar 注入式发射器，适配器 astream=ainvoke+队列排空（ADR-0008）
  - **重大实测发现：本机 CPU（无 CUDA，8 线程）Qwen3-Reranker-0.6B 约 15s/对，一轮 20 对约 5 分钟**→ 粗排预截断 rerank_max_candidates=20 + RERANK_ENABLED 开关（默认 true 忠实设计；本机 .env 置 false 走 RRF 降级序，GPU 机器可开启）
  - grounding 双规则（ADR-0006）：检索路径要求【来源：…】/信息不足声明；直接回答路径只查编造法条；Web/Plugin 未开通跳过校验
  - SSE 契约向后兼容：新增 status 事件（node/label/phase/duration_ms，中文标签映射 constants.NODE_LABELS）；ChatService/SSE 路由补显式分支（status 不进 delta 聚合）
  - 旧实现机械搬迁 _legacy/ 规避同名冲突（graph/nodes/prompts/state 四文件），BE-038 切换装配时删除；BE-030 置 deprecated
- 运行过的验证：
  - 每功能全量 pytest 保持绿：154→168→189→195→216→185（删旧 31 例）→197；干净环境重置后终验 **197 passed**（unit 127 含 agent 76 / integration 70 含 agent 12 / api 9；真实 Milvus 5 例不可达时跳过）
  - 前端 npm run build 通过；浏览器实操（GLM+真实 Milvus+专利法）：法律问题生成中浅色状态行实时滚动（含"正在检索知识库…"与子图节点）+「检索策略（N 条查询）」面板→done 后 16 节点状态保留+「参考文档 10」；第二个法律问题一次成功引用第七十一条赔偿规则并标注来源；闲聊直接回答（无检索策略、无"暂无依据"声明、仅主图节点状态）；grounding 双打回→兜底谨慎回答路径真实触发一次
  - 真实 E2E（verify_real_e2e.py，GLM+Milvus，RERANK 关闭）：上传 TXT/MD 均 201 ready→plan 携带检索策略→15 节点 status 贯通→回答正确引用第四十二条"二十年"并标注【来源】→sources 与持久化一致→事件序 plan<sources<delta
  - 图可视化：export_qa_graph.py 桩依赖重导出 15 节点 Mermaid（docs/qa_graph.mmd，内嵌 ARCHITECTURE §5）
  - 验证后已清理：law_chunks 集合 drop、backend/data 删除、前后端进程停止
- 已记录证据：feature_list.json BE-032~041、FE-014/015、BE-040（passing）+ BE-030（deprecated）；对账 56=36 热层（32 passing+4 deprecated）+20 archived
- 已知风险或未解决问题：
  - Rerank 精排在 CPU 机器默认关闭（RERANK_ENABLED=false 降级 RRF 序）——功能已验证可跑通，GPU 机器开启即得精排
  - grounding LLM judge 存在模型行为方差（GLM 偶发首答缺【来源】被规则档打回；重生成+兜底路径已验证兜住）
  - 每问题 LLM 调用 5~8 次（忠实设计 D3），本地 Ollama 部署首字延迟明显（PLANNER_PROVIDER=glm 缓解规划环节）
  - Ollama LLM 路径的真实模型 E2E 未跑（本轮 E2E 走 GLM 配置；图闭环行为由集成测试锁定）
- 下一步最佳动作：可选产品增强（会话重命名/停止按钮/CORS 收敛）、MySQL 8.0 接入、或 Web Search 二期（替换 Stub 即可，suggested_external_queries 已透传备用）

### Session 030（进度文档冷热分层：progress.md 与 feature_list.json 固定批量沉降）
- 日期：2026-09-12
- 本轮目标：两个进度文件只增不减导致膨胀（progress.md 554 行/30 个 Session，feature_list.json 369 行/千字级 evidence），建立冷热数据分层
- 技术决策：
  - 冷热边界：热层 = 当前状态（progress 头部 + 最近 Session；feature_list 全部非 passing 条目 + 最近 passing 条目），冷层 = docs/archive/ 按起止序号命名的只读分卷
  - 沉降机制唯一、首轮不特判：Session > 15 触发沉 10 个；passing 条目 > 40 触发沉 20 条（最旧优先），循环到触发线以内；冷分卷名 progress-archive-{起}-{止}.md / feature-archive-{起}-{止}.json
  - 关键不变量（写入 AGENTS.md）：不在 feature_list.json 热层中的功能条目均为 passing，完整条目见冷分卷；非 passing 必须显式留热层；顶层 archivedPassing.count 对账（全部功能数 = 热层条目数 + count）
  - 热层 evidence 规范：结论级 ≤200 字（日期 + 关键验证数字 + 结论 + 指针），过程细节随条目沉降
- 已完成：docs/archive/ 四个冷分卷（progress-archive-001-010.md、progress-archive-011-020.md、feature-archive-001-020.json）；progress.md 554→236 行（Session 021~029 共 10 个 + 头部归档指针）；feature_list.json 369→约 230 行（21 passing 压缩 evidence + 3 deprecated + archivedPassing 元数据）；AGENTS.md 新增"进度文档冷热分层规则"一节并更新开工流程第 5/6 步；clean-state-checklist.md 增加沉降检查项
- 运行过的验证：
  - 守恒校验：Session 总数 30 = 热 10 + 冷 10 + 10；功能总数 44 = 热层 24（21 passing + 3 deprecated）+ archivedPassing.count 20；沉降的 20 条 passing（BE-001~006、BE-009~022）整条原样进冷分卷，非 passing 全部留热层
  - feature_list.json 与 feature-archive-001-020.json JSON 语法校验通过（node JSON.parse）
- 已知风险或未解决问题：无
- 下一步最佳动作：OllamaProvider 加重试/降级（Session 028 遗留）

### Session 029（BE-031 LangGraph 问答图可视化导出脚本）
- 日期：2026-09-12
- 本轮目标：给 BE-030 的 LangGraph 问答图增加可复现的可视化出口，并把图固化进文档（应用户"有什么办法可视化看到图"的问题）
- 技术决策：
  - 桩依赖建图：build() 只装配节点不执行，_StubLLM/_StubRag 进构造函数即可——脚本零外部服务依赖（不需要 Milvus/Ollama/GLM），随时可跑，也是 DIP 可测试性的直接收益
  - 导出格式选 Mermaid 文本为默认（langgraph 内置 draw_mermaid()，GitHub 原生渲染、mermaid.live/VS Code 可交互查看），PNG 为 --png 可选项（draw_mermaid_png 依赖联网访问 mermaid.ink，失败时提示离线替代方案）
  - 图的可交互渲染版内嵌 ARCHITECTURE.md §5（紧随人工注解的 ASCII 图之后），并注明重生成命令——文档图与代码拓扑同源，不靠手维护
- 已完成：backend/scripts/export_qa_graph.py；docs/ARCHITECTURE.md §5 内嵌 Mermaid 图 + 条件边语义说明；docs/qa_graph.mmd 生成物
- 运行过的验证：
  - `cd backend && uv run python scripts/export_qa_graph.py` 成功：输出含 __start__/plan/retrieve/generate/verify/__end__ 六节点与全部边（plan→retrieve、generate→verify、retrieve -.replan.-> plan、retrieve -.-> generate 默认分支、verify -.replan/regenerate/end.->），条件边标签与 graph.py 路由语义一致；docs/qa_graph.mmd 写入成功
  - feature_list.json JSON 语法校验通过（uv run python json.load）
  - 全量测试 `uv run pytest tests -q` → 139 passed（提交后复跑确认）
  - **真实端到端（API 层）**：干净环境（删 data + reset_milvus）+ LLM_PROVIDER=glm + 真实 Milvus → verify_real_e2e.py 通过：上传专利法 TXT/要点笔记 MD 均 201 ready → 流式提问"发明专利权的保护期限"回答正确引用第四十二条"二十年"并注明来源 → sources 事件推送且持久化 assistant 消息 sources 一致
  - **浏览器界面实操（IAB，1280x720）**：①侧栏历史会话加载，消息/参考文档展开（5 条来源含文件名与条文）渲染正确；②新对话实时提问：plan 事件渲染"问题拆解（1 个子问题）"折叠列表 → delta 流式出答案 → done 后"参考文档 N"徽标出现，回答正确（十五年/十年）；③复杂问题触发"问题拆解（2 个子问题）"（适用条件/补偿上限各一），回答含结构化列表且引用第四十二条，参考文档 6 条；④知识库页：2 个文档"可检索"、删除文档走页面内二次确认，提示"文档已删除，相关向量数据已同步清理"（BE-029 Milvus 双清生效）；⑤删除会话：二次确认后侧栏移除、回到新对话空态；⑥整页截图检查布局/Markdown 列表/来源徽标渲染正常；⑦前端 npm run build（tsc + vite）通过
  - 界面测试观察项（低优先级）：输入框 fill() 后立即 Enter 一次未触发发送（疑似 React 受控更新竞态），点击发送按钮始终正常；上传控件依赖文件选择器，IAB 自动化不支持，上传路径由 API E2E 覆盖
  - 验证后已清理：law_chunks 集合 drop、backend/data 删除、前后端进程停止
- 已记录证据：feature_list.json BE-031（passing）
- 已知风险或未解决问题：无（本轮为工具脚本 + 文档，不动业务代码与测试）
- 下一步最佳动作：OllamaProvider 加重试/降级（Session 028 遗留的最值得做的独立功能）

### Session 028（BE-030/FE-013 统一 Plan-and-Execute 问答闭环：plan→retrieve→generate→verify + verify 反馈环）
- 日期：2026-09-12
- 本轮目标：应用户要求重构 Agent 图为统一规划闭环（不区分简单/复杂问题），verify 不合格可带建议打回 plan；一期到位（后端图 + SSE 协议 + 前端适配）
- 技术决策：
  - 统一拓扑：plan→retrieve→generate→verify；verify 三态判定（pass/grounding/contract）——依据不足带"无依据结论清单"回 plan 重规划，表达契约失败回 generate 重写，检索空命中回 plan（吸收 Self-RAG 改写逻辑）；预算 plan_runs≤2 / generate_runs≤2，超限放行 + WARN（防死循环）；简单问题 = planner 单子查询透传原问题的退化情形，无需问题分类路由
  - verify 两档：规则档（引用来源存在性、BE-017 信息不足声明、空回答）零成本先行；judge 档（groundedness，chat() 输出 JSON {verdict,feedback,unsupported}）做语义校验；judge 解析失败视为 pass——判分是增强不是闸门
  - PLANNER_PROVIDER 配置（follow/ollama/glm，默认 follow）+ PLANNER_MODEL：任务分解对模型能力最敏感，可强模型规划 + 快模型执行；containers._build_planner 工厂
  - RetrieveNode 多子查询合并：RagService.retrieve_queries 逐子查询 hybrid_search，按 chunk_id（兜底 document_id:chunk_index）合并保留最高分，截断 top6；sources 事件契约保持（有命中才推、先于当轮 delta；重规划后以最新一批为准）
  - SSE 协议扩展 plan/regenerating 事件（向后兼容，字段只增不改）；QaStreamEvent 值对象扩展 sub_queries 字段；chat_service 收到 regenerating 重置 delta 聚合；前端 subQueries 状态 + 生成中展示「问题拆解」
  - 关键修复：①retrieve 同时挂静态边与条件边 → replan 时 generate 在同一超级步并发执行写 verify_feedback 抛 InvalidUpdateError（删静态边）；②_route_after_retrieve 未查规划预算，空知识库会无限重规划（补 plan_runs 检查）；③test_settings 默认值断言补 LLM_PROVIDER delenv（pymilvus load_dotenv 副作用 Session 027 已记录，.env 换 glm 后该测试也暴露）
- 运行过的验证：
  - 干净环境（删 backend/data + reset_milvus.py）`uv run pytest tests -q` → **139 passed**（unit 62 / integration 68 / api 9；新增 test_agent_parsing 13 例，test_agent_graph 重写 19 例：单子查询退化/多子查询合并去重/grounding 打回建议传递/contract 打回 generate/预算耗尽降级/plan→sources→delta 事件顺序/regenerating 后 delta 重置拼接/ainvoke 同路径，test_api 适配 plan 先行断言）
  - 前端 `npm run build`（tsc 类型检查 + vite）通过
  - 真实 E2E（当前 .env 配置 LLM_PROVIDER=glm + 真实 Milvus + 专利法上传）：plan 事件携带 2 个真实子查询（"发明专利权的保护期限"/"发明专利权保护期限的法律依据"）→ sources 6 条合并 → **规则档 contract 触发一次 regenerating（首轮回答未注明来源）** → 第二轮正确引用第四十二条"二十年" → user/assistant 持久化且 sources 一致；验证后进程与数据（data + law_chunks 集合）已清理
- 已记录证据：feature_list.json BE-030 / FE-013（passing，含上述细节）；ARCHITECTURE §5（目标图与预算）/§6（PLANNER_* 配置）/§7（SSE 协议）/§9（139）同步；PRODUCT.md 第 3 节新增拆解展示与自动校验重生成行为
- 已知风险或未解决问题：
  - 每次问答 LLM 调用 3~4 次（plan 1 + generate 1~2 + judge 1）：本地 Ollama 部署延迟明显增加，建议 PLANNER_PROVIDER=glm；**OllamaProvider 仍无重试**，统一 plan 后调用次数变多，无重试风险放大——下一轮最值得做的独立功能
  - Ollama LLM 路径的真实模型 E2E 未跑（本轮 E2E 走 GLM 配置；图的闭环行为已由集成测试锁定）
  - judge 用主模型（跟随 LLM_PROVIDER），本地小模型判分质量未做专项评估（解析失败会安全放行）；verify 规则档依赖回答含"【来源："字面，与 Prompt 约定强耦合，模型换风格可能误判（judge 档兜底）
  - 浏览器 GUI 层本轮未截图验证（build 类型检查 + SSE 事件消费已验证）
- 下一步最佳动作：OllamaProvider 加重试/降级；或可选产品增强（会话重命名/停止按钮/CORS 收敛）或 MySQL 8.0 接入

### Session 029（移除 rag=None 兼容：rag 成为问答工作流必选依赖）
- 日期：2026-09-12
- 本轮目标：用户确认 create_qa_workflow 不会出现 rag 为 None 的情况，删除全部 rag=None 基础工作流兼容代码
- 改动内容：
  - `agent/graph.py`：QaGraphBuilder/build_qa_graph 的 rag 参数改为必选（`RagService`，去掉 `| None`），build() 删除 rag is None 分支——图拓扑唯一：plan→retrieve→generate→verify；"无知识库"场景由空命中重规划路径承接（预算用尽后空 context 进 generate 走 BE-017 信息不足策略）
  - `agent/__init__.py`：create_qa_workflow(llm, rag: RagService, planner=None)，rag 必选
  - `agent/state.py`：context 注释更新（空串 = 知识库空命中）
  - `scripts/verify_ollama_stream.py`：改为构造 RagService 传入（空库走信息不足策略）
  - 测试：test_agent_graph.py 重构为 rag_factory 夹具（content=None 即空知识库），原"基础工作流"用例全部改为空知识库场景（空命中重规划吃满预算后走信息不足，plan_calls==2 成为新断言）；装配守卫用例同步适配
  - 文档：ARCHITECTURE §5 删除"基础工作流"拓扑与 rag=None 表述，rag 标注为必选依赖
- 运行过的验证：干净环境（删 backend/data + reset_milvus.py）`uv run pytest tests -q` → **139 passed**（数量不变，用例改写不增减）
- 已知风险或未解决问题：无新增；测试容器（test_api.py）不受影响（始终注册真实 RagService）
- 下一步最佳动作：同 Session 028（OllamaProvider 重试优先）

### Session 027（BE-029 向量库全面迁移到 Milvus hybrid_search）
- 日期：2026-09-12
- 本轮目标：用户要求"全面改为 Milvus 进行 hybrid_search 来解决（BE-028 自研 BM25 全量重建）问题，chroma 相关代码全部删掉"
- 技术决策：
  - **单一 Milvus 集合承载混合检索**：稠密 FLOAT_VECTOR(COSINE) + 稀疏 SPARSE_FLOAT_VECTOR；content 字段启用 jieba 分词器 + BM25 Function（服务端自动生成稀疏表示，客户端零分词逻辑）；hybrid_search 一次调用发起两路 AnnSearchRequest，服务端 RRFRanker(k=60) 融合——BE-028 的全量重建问题、双写双清编排、JSON 快照、自研 RRF 函数全部随之消失
  - **端口演进**：VectorStore.search(query_embedding) 升级为 hybrid_search(query_text, query_embedding, top_k, min_score)；接口以"知识库混合检索"能力命名，调用方不感知融合细节
  - **一致性实测结论**（探针脚本对真实 v3.0.0 验证）：必须 consistency_level="Strong"——默认 Bounded 下新插入数据不可见，且 hybrid_search 空结果触发 Milvus 已知缺陷 #50969（误报 unsupported ID type），曾据此误判 VARCHAR 主键不支持；min_score 经稠密请求 range search(radius) 实现，min_score<=0 时不加 radius（COSINE range 为严格大于，radius=0 会误滤 0 分结果）；主键结果以字段名 chunk_id 返回而非固定键 id
  - **集合懒建**：首次 add_chunks 按实际 embedding 维度建集合（测试 64 维确定性 embedding 与生产 768 维 nomic 都无需配置）；检索在集合不存在时返回空（空知识库语义）；document_id 上 INVERTED 索引支撑按文档删除
  - **删除清单**：chroma.py、KeywordIndex 端口、Bm25KeywordIndex、reciprocal_rank_fusion、test_keyword_index/test_rag_fusion/test_chroma_vector_store/test_hybrid_retrieval；依赖 chromadb/jieba/rank-bm25 卸载，pymilvus 3.0.1 入列；settings 删除 CHROMA 枚举/chroma_persist_dir/bm25_index_path/HYBRID_SEARCH_ENABLED（默认 milvus），并加回归断言 vector_store_provider=chroma 被拒绝
  - **测试封闭性策略**：新增 tests/fakes.py 共享 InMemoryVectorStore（余弦 + 子串词面 + RRF 近似，遵循混合检索契约），API/Agent/RAG/Embedding 集成测试全部改用 Fake；唯一例外是新增 test_milvus_vector_store.py 5 例需真实 Milvus，服务不可达时 skip 并注明
  - **发现并记录的第三方行为**：pymilvus 在 import 时调用 load_dotenv 把 backend/.env 灌入进程环境——敏感配置测试改为先 delenv 再断言默认空值（测试注释已说明）
  - docker-compose.yml 无需更新（etcd+minio+milvusdb/milvus:v3.0.0 standalone 已就绪）；PRODUCT.md 无改动（用户可见行为不变）
- 运行过的验证：
  - 探针脚本对真实 Milvus v3.0.0 实测 schema/插入/hybrid_search/radius/删除/空结果路径（一次性脚本，验证后删除）
  - 干净环境（删 backend/data + scripts/reset_milvus.py）uv run pytest → **119 passed**（含真实 Milvus 5 例；分层 unit 50 / integration 60 / api 9）
  - 真实端到端（uvicorn 8013，GLM glm-4.5-air + Ollama nomic-embed-text + 真实 Milvus）：上传专利法 TXT 201 ready（VectorStore connected 日志 collection_exists=false → 首次入库懒建）→ 流式提问"发明专利权的保护期限是多长时间？"→ sources 事件 4 条先于 delta、来源含第四十二条"二十年" → 回答正确引用"发明专利权的期限为二十年，自申请日起计算" → 消息持久化且 sources 回读一致 → 删除文档 204 后 Milvus 集合 count(*)=0；检索日志 hit_count=4/top_score≈0.032（双通道 RRF 叠加）
  - Ollama LLM 路径本机仍故障（llama-server 500，Session 025 已知问题），以 GLM Provider 等价验证
  - 补充端到端复测（2026-09-12，Session 027 收尾后追加）：标准脚本 verify_real_e2e.py 全部断言通过（干净环境 + GLM——专利法 TXT 与要点笔记 MD 均 201 ready，31 chunk 入 Milvus 集合；回答正确引用第四十二条"二十年"；sources 契约与持久化一致）；新增词面精确查询专项（"专利法第五十五条具体规定了什么内容？"→ 回答精确引用第五十五条强制许可条款，验证 BM25 通道对法条编号词面匹配的价值）；删除两份文档后集合 count(*)=0（级联清理）；测试会话已清理，验证后环境重置
  - 验证后进程清理、端口释放、backend/data 与 law_chunks 集合重置
- 已记录证据：feature_list.json BE-029（passing）、BE-007/008/028（deprecated，历史证据指向 git 历史）
- 已知风险或未解决问题：
  - **测试套件封闭性出现唯一例外**：test_milvus_vector_store.py 需要真实 Milvus（docker compose up -d），否则 5 例 skip——已写入 ARCHITECTURE §9 与 RELIABILITY
  - **干净环境重置多了一步**：删除 backend/data 之外还需 `uv run python scripts/reset_milvus.py`（RELIABILITY.md 已更新）
  - **pymilvus import 副作用**：load_dotenv 会把 .env 灌入进程环境，业务代码若直接读 os.environ 会读到 .env 值（当前全部经 settings 读取，无实际影响，已记录）
  - **MILVUS_URI 默认指向 127.0.0.1:19530**：部署形态变化（本机需常驻 Milvus 容器），启动前置条件从"无"变为"Milvus 可达"
  - 既有遗留项不变：MySQL 未启用、无连接池、min_score 默认 0.0、Ollama 0.32.0 崩溃
- 下一步最佳动作：可选产品增强（会话重命名 / 停止按钮 / 深色主题开关 / CORS 收敛 / OllamaProvider 重试）或 MySQL 8.0 接入

### Session 026（BE-028 RAG 混合检索：BM25 关键词 + 向量，RRF 融合）
- 日期：2026-09-12
- 本轮目标：用户要求"将原先的 RAG 检索更改为使用 BM25 的混合检索"
- 技术决策：
  - **架构形态**：新增并列检索通道而非改造向量库——KeywordIndex 领域端口（domain/repositories/keyword_index.py，与 VectorStore 端口同构 add/search/delete_by_document）+ Bm25KeywordIndex 基础设施实现（infrastructure/keyword_index/bm25.py，jieba 分词 + rank_bm25 的 BM25Okapi）；RagService 双通道检索后用 RRF（Reciprocal Rank Fusion，k=60）融合
  - **为什么 RRF 而非加权分数**：BM25 分数与余弦相似度量纲不同不可直接加权；RRF 只用排名，无需调权，对分数分布不敏感；同一 chunk 两路同时命中得分叠加，天然去重且排前（结果 score 改写为 RRF 得分，保持"越大越相关"契约）
  - **语料持久化**：BM25 语料快照 JSON（backend/data/bm25_index.json，临时文件 + os.replace 原子写），与 Chroma 同目录随干净环境重置一并清除；写入失败降级为 WARN 日志不上抛（向量库已写成功，不能因快照盘写失败把文档打成 failed）；进程内全量重建 BM25（当前规模代价可忽略，换来"模型与语料一致"的结构保证）
  - **一致性编排**：入库双写（KnowledgeIngestionService，在向量库写入之后——复用 Chroma 生成的 chunk_id，RRF 去重依赖两路 id 一致）、删除双清（DocumentService，日志新增 keyword_removed_chunks）；一致性由这两处唯一编排保证，调用方无感
  - **小语料 IDF 归零兜底**：BM25Okapi 在语料仅 2 条时所有 IDF 为 0、得分全 0（实测发现）；命中判定改为按词面相交（词面不相交直接排除），排序按 (BM25 分数, 命中词数) 双键兜底，写入顺序稳定
  - **回退开关**：HYBRID_SEARCH_ENABLED（默认 true）在装配点判断，false 时不注入关键词索引，RagService 优雅降级为纯向量；开关属装配决策，不进业务服务
  - min_score 语义保持不变：仍只过滤向量通道（融合之前）；DDD 边界守护名单加入 jieba/rank_bm25（关键词检索技术栈锁定在 infrastructure）
  - 用户可见行为不变（PRODUCT.md 无改动）：sources 事件契约、【来源：文件名】标注、"信息不足"策略全部保持
- 运行过的验证：
  - 基线：干净环境（删 backend/data）uv run pytest → 117 passed
  - `uv run pytest tests -q` → **134 passed**（新增 17：test_keyword_index 7 + test_rag_fusion 6 + test_hybrid_retrieval 4）；分层 unit 61 / integration 64 / api 9
  - 真实端到端（干净环境，8013 端口，Ollama qwen3.5:4b + nomic-embed-text）：上传专利法 TXT → 29 chunk 双写入库（bm25_index.json 可查、UTF-8 文件名正常）→ 流式提问"发明专利权的保护期限是多长时间？"→ sources 事件 4 条先于 delta → 回答正确引用"二十年"（第四十二条）→ 消息持久化且 sources 回读一致 → DELETE 文档 204 后 bm25 快照归零（双清）；检索日志 `RAG hybrid retrieval completed` 显示 vector_hits=4 / keyword_hits=4 / top_score≈1/61+1/62（双通道叠加生效）
  - 回退开关实测：HYBRID_SEARCH_ENABLED=false 启动（8014）→ 日志 hybrid_search_enabled=false、无 KeywordIndex initialized → 流式问答纯向量路径正常
  - 对照观察（单次抽样，非严格对照）：同一问题混合模式回答引用"二十年"、纯向量回退未引用——BM25 对法条词面召回的价值得到真实体现
  - 验证后进程已清理、端口已释放、backend/data 已重置
- 已记录证据：feature_list.json BE-028（passing，含完整 evidence）；ARCHITECTURE §1/§2/§3/§4/§6/§9、RELIABILITY service 清单（新增 keyword_index）、.env.example 同步
- 已知风险或未解决问题：
  - BM25 语料快照与 Chroma 是两份独立存储：仅靠"同目录、同编排"保持一致，若绕过 API 手工删其一，另一路会残留（文档已注明；单路残留时检索仍优雅降级）
  - BM25Okapi 每次增删全量重建：当前规模（数百 chunk）无感，知识库到万级 chunk 时需评估增量结构
  - 双 uvicorn 实例并存时第二个实例可能因 OpenBLAS 内存分配失败启动崩溃（环境问题，与本功能无关，单实例正常）
  - 既有遗留项不变：MySQL 未启用、无连接池、min_score 默认 0.0
- 下一步最佳动作：可选产品增强（会话重命名 / 停止按钮 / 深色主题开关 / CORS 收敛 / OllamaProvider 重试）或 MySQL 8.0 接入

### Session 025（删除非流式问答死代码 send_message + ARCHITECTURE §5 图拓扑图形化）
- 日期：2026-09-11
- 本轮目标：用户要求①确认非流式问答接口不存在且 send_message 无调用后删除之；②ARCHITECTURE.md 第 5 节以图的形式表现代码中的 LangGraph 图（随后要求简化为只表达节点流转）
- 技术决策：
  - 调用面核实：`send_message` 在路由、测试、脚本中零调用（接口层唯一问答端点是 `POST /api/chat/stream`），判定为死代码；且其内部本就不持久化 assistant 回答、丢失 sources，与流式路径行为漂移，删除优于修补
  - 删除范围仅限 `ChatService.send_message`：`QaWorkflow.ainvoke` 端口与 `run_qa`/`build_qa_graph` 兼容入口保留（test_agent_graph.py 经它们以非流式方式测图，属图引擎能力而非业务接口）
  - 先文档后代码：ARCHITECTURE.md §4"流式与非流式执行同一节点"改写为"对外唯一入口是 SSE 流式接口，图引擎仍支持 ainvoke（测试与脚本使用）"；§5 拓扑小节改为图形化 LangGraph 图（节点流转 + 单行职责注记：写状态、推事件），按用户要求从展开版简化为简洁版
  - chat_service.py 模块 docstring 与注释同步（不再提"两条路径"）
- 运行过的验证：
  - 干净环境（先删 `backend/data`）`uv run pytest tests -q` → **117 passed**（数量与基线一致，无测试依赖 send_message）
  - 真实启动 smoke（8012 端口）：启动日志全链正常（Application configured → Database directory created → Database initialized → VectorStore initialized），`/api/health` ok、`/api/conversations` 返回 `[]`；验证后进程已清理、端口已释放
  - 端到端（clean-state-checklist 新增要求）：本机 Ollama 的 llama-server 进程崩溃（`exit status 0xc0000409` 栈溢出，直接 curl `/api/chat` 亦失败，与本轮改动无关的模型服务侧故障），改以 `LLM_PROVIDER=glm`（glm-4.5-air，.env 已有密钥）走真实 E2E——上传专利法 TXT+MD 入库 → 流式 RAG 问答正确引用第四十二条"二十年" → sources 事件契约（4 条、先于 delta、source/content 齐全）→ user/assistant 持久化且 assistant sources 与流内一致。**E2E PASS**
  - 运维备注：Git Bash 的 `kill` 杀不掉 Windows PID 的监听进程（新 uvicorn 绑定 8000 失败静默退出，旧 Ollama Provider 进程继续服务导致误判）；必须 `netstat -ano` 找 PID 后 `taskkill //PID //F`
- 已记录证据：本轮为死代码清理与文档同步，feature_list.json 无功能状态变化（BE-001~027 与 FE-001~012 保持 passing，文件 JSON 校验通过）
- 已知风险或未解决问题：
  - **本机 Ollama 0.32.0 llama-server 进程崩溃未恢复**（原"上传后偶发 500"恶化为持续 500）：E2E 的 Ollama 路径本轮无法验证，需重启 Ollama 服务后补验；GLM 路径已验证通过
  - 既有遗留项不变：MySQL 未启用、无连接池、min_score 默认 0.0
- 下一步最佳动作：可选产品增强（会话重命名 / 停止按钮 / 深色主题开关 / CORS 收敛 / OllamaProvider 重试）或 MySQL 8.0 接入

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
