# Agent 模块一期重写计划（v3）

> 依据：`legal_agent_phase1_technical_design.md`（LangGraph 法律助手一期技术设计）。
> 目标：对 `backend/app/agent/` 整体重写——主图轻量编排 + 独立 Local Legal RAG 子图 + Web/Plugin Stub + 服务层。
> 状态：计划已获用户批准（2026-09-13）。逐功能实施，进度见 progress.md 与 feature_list.json。

## 探索结论（已确认事实）

- 设计文档要求：主图（query_router→orchestrator→action_router→Capability→observation 循环→answer_generator→grounding→final/fallback）+ 独立 Local Legal RAG 子图（retrieval_planner→strategy_router→rewrite/subquery/expansion→hybrid_retriever→evidence_ranking→evidence_grader→recovery 循环→rag_result）+ Web/Plugin Stub + services 层，30 条强制约束已逐条核对。
- `QaWorkflow` 端口与 SSE 协议保持**字段只增不改**的向后兼容扩展；ChatService 不重写，仅增分支。
- rerank 模型 Qwen3-Reranker-0.6B 本地快照就绪；sentence-transformers 6.0.1 / torch 2.14.0 已装入 venv（pyproject 已改未提交）。
- DDD 边界守护：langgraph 仅限 app/agent/；新增 sentence_transformers/torch 隔离条目。
- 可复用：VectorStore 端口（Milvus 服务端 hybrid_search=Dense+BM25+RRF）、EmbeddingService、LLMProvider、RagService、tests/fakes.py。

## 用户已确认的产品决策

| # | 决策 | 落点 |
|---|---|---|
| D1 | 「拆解展示」改为检索策略全量展示：plan 事件携带全部检索查询（original+rewrite+subquery+expansion 去重后 ≤8 条），前端文案改「检索策略（N 条查询）」 | PRODUCT.md §3、FE-014、ADR-0005 |
| D2 | 直接回答路径：一般性问题（问候/概念解释/系统说明）跳过检索直接回答，不显示检索策略、不再声明"暂无依据"；法律事实型问题默认走知识库检索 | PRODUCT.md §3、BE-036、ADR-0006 |
| D3 | 忠实设计：全部 LLM agent 按设计实现；本地 Ollama 延迟用 PLANNER_PROVIDER=glm 缓解 | BE-036、风险 |
| D4 | rerank 后证据 10 条（设计默认），进上下文与「参考文档」 | LegalRAGConfig.rerank_top_k=10 |
| D5 | 节点运行状态流式展示（Codex 风格浅色小字）：后端每个节点开始/结束时向前端推 status SSE 事件，前端以浅灰小字实时渲染执行过程，完成后保留显示 | BE-041、FE-015、ADR-0008、PRODUCT.md §3 |

## Grilling 补齐的行为规则（先写 PRODUCT.md 再实现）

1. plan 事件 = 每轮检索规划的全部查询（重规划/恢复轮覆盖推送）；无检索的轮次（direct/web/plugin/finish）无 plan 事件。
2. AppContext.sendQuestion 发起新提问时清空 subQueries 与 nodeStatuses。
3. Web/Plugin 请求：stub 返回 NOT_IMPLEMENTED/DISABLED 后由 answer_generator 生成"该功能尚未开通"的说明性回答，不编造结果。
4. 证据不足展示：有部分证据 → 谨慎回答 + 正常展示参考文档；完全无命中 → "知识库中暂无相关依据，建议咨询专业律师" + 无参考文档。
5. grounding 规则适配：RAG 路径维持原规则（有依据必须【来源：…】、无命中必须声明信息不足）；direct 路径只校验"不编造法条/案例编号"。
6. 延迟风险：每问题 LLM 调用 5~8 次（D3 已接受），节点 latency 埋点 + 文档标注。
7. D5 状态展示规则：每个图节点（主图 + RAG 子图全部节点）开始时推 `status(phase=start)`、结束时推 `status(phase=end, duration_ms)`；前端按序渲染浅色小字行——开始为"正在{label}…"，结束补耗时；done 后保留；regenerating 后跨轮次累加不重置；label 中文映射表放 agent/constants.py；observation/action_router 等瞬时确定性节点同样推送。

## SSE 协议扩展（D5 核心，字段只增不改）

```json
{"type": "status", "node": "hybrid_retriever_node", "label": "检索知识库", "phase": "start"}
{"type": "status", "node": "hybrid_retriever_node", "label": "检索知识库", "phase": "end", "duration_ms": 812}
```

- 图构建器用统一包装器包裹全部节点（建造者层 DRY，节点零改动）——包装器在节点执行前后推 status 事件并写 trace（设计 §48）。
- QaStreamEvent 领域值对象扩展 type="status" + node/label/phase/duration_ms 可选字段。
- ChatService 增 status 分支：仅转发、不参与 delta 聚合。
- 事件顺序：status 与既有事件交织，test_api 序列断言放宽为"过滤 status 后保持原序"。

## 架构映射决策（ADR 化，实施时创建 docs/adr/ 与 docs/glossary.md）

1. 目录：设计 `agent/` → `backend/app/agent/`；设计 `agent/tests/` → `backend/tests/{unit,integration}/agent/`。
2. 服务层适配领域端口：MilvusService→VectorStore 端口（不直连 SDK）；LLMService→LLMProvider，structured_invoke=chat+JSON 容错+重试 1 次+安全默认（Planner 默认 original、Grader 默认 insufficient）；RerankerService 新增（CrossEncoder CPU、懒加载单例、失败降级 RRF 序 + reranker_degraded）。
3. SSE 映射：plan=检索规划全部查询；sources=rag_result_node 的 ranked_evidence（先于该轮 delta）；delta=answer 流式；regenerating=已有 answer 再次流式前必推；status=节点起止（D5）。
4. 流式策略：answer_generator 是 finish 路径唯一流式出口；direct_answer_agent 直接流式；direct 已有完整草稿时 answer_generator 透传。
5. 多选策略 fan-out：strategy_router_node 条件边返回目标列表并发执行 LLM 策略 agent（各写独立 state 键防 InvalidUpdateError），original 由 strategy_router 直接写入 retrieval_queries；hybrid_retriever 内 asyncio.gather 并发检索。
6. 预算：主循环 max_global_steps=4（orchestrator 超限强制 finish；grounding 打回在条件边查预算，超限走 fallback）；RAG recovery max_retries=2；两预算独立。
7. 配置：agent/config.py 数据类（默认值按设计 §43），containers 从 Settings 构造；Settings 新增 RERANKER_MODEL_PATH 等 + .env.example 同步。
8. 去重与重排：chunk_id > document_id:chunk_index > 内容哈希，多 query 命中合并 matched_queries；evidence_ranking 用 original_query 统一 rerank。
9. BE-030 → deprecated（BE-038 切换时标记）；BE-031 export 脚本适配新图保持 passing；旧 agent 文件与旧测试（test_agent_graph/test_agent_parsing）在切换装配时删除。

## 功能拆分（feature_list.json）

| ID | 名称 | 内容 |
|---|---|---|
| BE-032 | Agent 重写骨架 | 目录结构、主图/RAG 的 state/config/schemas/constants（含节点 label 映射）、utils（Phase A） |
| BE-033 | Agent 服务层 | LLMService/MilvusService/RerankerService/CitationService + Settings 扩展 + .env.example（Phase B） |
| BE-034 | Local Legal RAG 核心节点 | 10 节点 + legal_rag/prompts 6 文件（Phase C） |
| BE-035 | Legal RAG 子图组装 | build_legal_rag_graph + recovery 预算路由，独立 ainvoke 可跑（Phase D） |
| BE-036 | 主图节点 | 9 节点 + prompts 6 文件；direct/web/plugin 的 grounding 规则适配（Phase E） |
| BE-037 | Web/Plugin Stub | entry+stub 各 2 节点，仅 NOT_IMPLEMENTED/DISABLED（Phase F） |
| BE-038 | 主图组装与装配切换 | build_agent_graph、SSE 映射、create_qa_workflow 新签名、containers 接线、删旧 agent 文件（Phase G） |
| BE-041 | 节点状态流式事件 | 统一节点包装器（起止计时+trace+status 推送）、QaStreamEvent 扩展、ChatService status 分支、子图事件传播验证（Phase G+） |
| BE-039 | 测试体系重建 | unit/integration/agent（子图 7 场景、主图 E2E 5 case、SSE 序列含 status、direct 路径、stub）、fakes 扩展、DDD 边界更新、删旧测试（Phase H） |
| FE-014 | 前端检索策略展示与直接回答适配 | 文案改「检索策略（N 条查询）」、sendQuestion 清空 subQueries、build+浏览器回归 |
| FE-015 | 前端节点状态浅色展示 | types 扩展 status 事件、chat.ts onStatus、AppContext nodeStatuses、MessageBlock 浅色状态行、build+浏览器回归 |
| BE-040 | 文档/可视化/真实 E2E 收尾 | ARCHITECTURE §2/§3/§5/§7/§9 重写、PRODUCT.md 行为变更、RELIABILITY 清单、docs/adr/0001~0008 + docs/glossary.md、export_qa_graph 适配重导出、verify_real_e2e 适配+真实运行、progress/handoff/checklist 收尾 |

## 执行序列（每功能：先文档→代码→验证→标 passing→提交）

1. 开工验证：init.md 检查 + 干净环境全量 pytest 基线（139）✅（2026-09-13 实测通过）。
2. 提交 1（文档先行）：plan.md + feature_list.json 拆分 + PRODUCT.md 行为变更初稿 + ADR-0001/0002。
3. BE-032~BE-038 顺序实现：新旧 agent 并存不接装配点，每步全量 pytest 保持绿，随实现补 ADR。
4. BE-041：状态事件包装器 + 协议扩展 + chat_service 分支（含子图传播专项测试，失败则降级为注入式事件发射器）。
5. BE-039：测试体系落地（删 32 旧、新增约 65+，总数以实测为准）。
6. FE-014 + FE-015：前端两项适配 + npm run build + 浏览器实操。
7. BE-040：文档重写、ADR/glossary 齐、重导出 qa_graph、真实启动 smoke、真实 E2E → 收尾三件套 + 沉降对账。
8. 每功能一次清晰提交。

## 风险与对策

- 子图内 get_stream_writer 事件是否上浮到主图 astream：BE-041 首项专项测试；不传播则降级为构建期注入共享事件发射器。
- rerank CPU 延迟 1~3s：懒加载 + 失败降级 RRF。
- fan-out 并发写冲突（Session 028 踩坑）：各策略 agent 只写独立 state 键，retrieval_queries 仅由 strategy_router 汇总。
- LLM 调用次数增加（D3 已接受）：PLANNER_PROVIDER=glm 缓解 + 每节点 latency 埋点。
- 测试封闭性：reranker 真实模型不进自动化测试（Fake 替换），仅 E2E 验证。
- LLM 结构化输出可靠性：JSON 容错 + 重试 1 次 + 安全默认，脚本化 Fake 覆盖回退路径。

---

# 二期增强：思考块（Thinking Panel，BE-042 + FE-016）

> 依据：2026-09-13 用户需求「浅颜色字体统一归类为『思考』tag，可点击展示/收起（默认展示），答案输出完整时收起，且浅色字不仅表示运行节点，还要打印运行内容与 LLM 输出」。
> 状态：grilling 定稿（ADR-0009），文档先行，代码未动。

## 用户已确认的产品决策

| # | 决策 | 来源 |
|---|---|---|
| D6 | 现有浅色过程行（节点状态 FE-015）+「检索策略」面板（FE-014）+ 新增内容行统一归入一个「思考」块容器，置于回答上方；生成中默认展开 | 用户原话「统一归类为『思考』tag，默认展示」 |
| D7 | 回答输出完成后思考块**自动收起为一行摘要**（「已完成思考 · Ns」+ 展开箭头），点击可展开/收起（DeepSeek 式交互） | 用户选项「收起为一行」 |
| D8 | 思考内容范围（在节点状态行之外新增四类）：① LLM 决策输出（意图判定/编排决策/证据评估/校验判定等）② 检索运行细节（命中数/重排降级/采用证据数）③ 检索策略并入思考块 ④ 重写/兜底流转过程 | 用户多选全选 |
| D9 | 详细程度 = **原文截断打印**：非结构化 LLM 输出直接打印原文，超长截断；结构化 JSON 输出把关键字段拼成一句中文后再截断；截断上限 **120 字**，由**后端发事件前统一截断**（前端零截断逻辑） | 用户选「原文截断打印」+ 推荐默认（120 字/JSON 拼句） |
| D10 | 思考内容**刷新后不保留**（客户端内存快照，与现状一致；不改数据库 schema） | 用户选「刷新后不保留」 |
| D11 | 闲聊/直接回答路径**同样展示思考块**（内容行少、无检索相关条目，交互全站一致） | 推荐默认 |
| D12 | 回答**出错时保留思考块**（现状清空 → 改为保留，便于定位出错前执行到哪一步；错误提示仍单独显示） | 推荐默认 |

## Grilling 补齐的行为规则（先写 PRODUCT.md 再实现）

1. think 事件 = 节点内打印的一条思考内容行；与 status 事件互补：status 表节点起止，think 表过程内容；同一节点可发多条 think。
2. 检索策略并入：plan 事件契约不变（全部检索查询），前端把 sub_queries 渲染为思考块内「检索策略（N 条查询）」一节（有序号列表）；重新规划时覆盖该节。
3. regenerating/兜底流转由后端发 think（如「回答未通过依据校验，自动重写中」「依据校验未通过且预算耗尽，生成谨慎回答」）——前端不自行合成流转文案，单一事实源在后端。
4. 节点→内容清单（BE-042 落地范围）：query_router=意图判定；orchestrator=编排决策；strategy_router=选中策略；hybrid_retriever=查询数与命中数；evidence_ranking=重排启用/降级与保留条数；evidence_grader=评估结论；recovery_planner=恢复计划；grounding_checker=校验判定+理由；finish 路由=兜底触发说明；web/plugin stub=未开通说明；final_answer=引用来源条数；observation/direct_answer/answer_generator 不发（避免与回答本体重复）。
5. 思考块收起后的总耗时 = 首个 status(start) 到最后一个 status(end) 的墙钟时间（前端计时，与节点耗时合计无关）。
6. 出错保留：onError 不再清空思考行（现有 setNodeStatuses([]) 行为移除）；新提问仍清空重新记录。
7. 历史消息（刷新/重开）不显示思考块——消息快照仅存当前浏览会话内存。
8. 截断工具 `truncate_text(text, 120)` 放 agent/utils；think 事件 text 保证 ≤120 字（契约），前省略号结尾。

## SSE 协议扩展（D8/D9 核心，字段只增不改）

```json
{"type": "think", "node": "evidence_grader_agent", "label": "评估证据充分性", "text": "证据评估：已有证据充分，10 条证据支撑回答"}
```

- `type` 增加 `"think"`；字段 node/label/text（label 复用 NODE_LABELS 映射）；text 已由后端截断。旧前端对未知事件类型静默忽略，向后兼容（ADR-0002 口径）。
- ChatService 增 think 显式分支（仅转发，不进 delta 聚合）；SSE 路由增 think 帧映射。
- test_api 序列断言放宽为「过滤 status 与 think 后保持原序」。

## 功能拆分（feature_list.json）

| ID | 名称 | 内容 |
|---|---|---|
| BE-042 | 思考事件流式输出 | truncate_text 工具、QaStreamEvent 扩展 think、各节点按清单发 think（JSON 拼句）、ChatService/SSE 分支、单测+集成事件序+api 断言放宽 |
| FE-016 | 前端思考块 | types/chat.ts 增 think、AppContext 统一思考行列表（status 合并+think 追加、新提问清空、出错保留）、MessageBlock 思考块容器（生成中默认展开/完成后收起一行/点击切换、检索策略并入、快照挂消息）、build+浏览器回归 |

## 执行序列

1. 文档先行（本次）：plan.md + ADR-0009 + glossary + PRODUCT §3 + ARCHITECTURE §7 + feature_list（planned）→ 提交。
2. BE-042 后端：工具→事件→节点→服务层→测试（全量 pytest 保持绿）→ 提交。
3. FE-016 前端：types→AppContext→MessageBlock→npm run build→浏览器实操→ 提交。
4. 收尾：真实 E2E 断言 think 事件 + 浏览器三场景回归 + progress/session-handoff/feature_list evidence + 沉降对账。

## 风险与对策

- think 事件量增加（每问题约 10~15 条）：浅色小字+可收起语义下可接受；SSE 单帧 <300 字节。
- LLM 原文含英文/JSON 碎片：JSON 决策一律拼句（D9）；非结构化输出（grounding 理由）接受原文截断。
- 前端状态复杂化：思考行统一数组（status 合并 + think 追加）替代现有 nodeStatuses 双状态，FE-015 语义保留为其中 status 行。

---

# 三期增强：Langfuse 全链路 trace（BE-043）

> 依据：2026-09-13 用户需求「项目中使用 langfuse 做 trace，并且开关作为配置放在 .env 中」。
> 状态：文档先行（ADR-0010），代码未动。

## 设计决策（ADR-0010 摘要）

1. **可观测汇走领域端口**：`domain/services/trace_sink.py` 定义 `TraceSink`/`TraceSpan` 协议 + `trace_sink_var`（ContextVar，stdlib 零依赖）——与 ADR-0008 事件机制同构的"ContextVar 注入式汇"；langfuse SDK 锁在 `infrastructure/trace/`（DDD 守护名单加 langfuse）。
2. **trace 生命周期归 ChatService**（应用层）：请求开始 `start_trace(session_id=conversation_id, input=question)`；plan/think/sources/regenerating 经 `record_event` 记为 trace 事件；正常结束 `end_trace(output=完整回答)`，异常 `end_trace(error=...)` 后原样上抛。
3. **节点 span 归 with_node_status 包装器**（agent 层，DRY 与 status 同一机制）：节点执行前 `start_span(node, parent=当前栈顶)` 压入 `trace_span_var`，结束 `span.end(duration_ms, error)` 弹出——异常也 end；子图复合节点天然形成父子嵌套。
4. **LLM generation 归 LLMService**（agent 层，模型调用唯一入口）：invoke/structured_invoke（含重试轮次）/stream 三条路径都经当前 span 记 generation（model + messages + output + 耗时 + attempt）。
5. **开关与装配**：Settings 新增 `langfuse_enabled`（默认 false）/`langfuse_base_url`/`langfuse_public_key`/`langfuse_secret_key`（BASE_URL 命名与用户 .env 预置及 SDK 自身口径一致）（密钥只走 .env，不进仓库不进日志）；containers 按开关注入工厂——关闭时 ChatService/LLMService 拿到 None，零开销零 langfuse import；开启但缺密钥 → WARN 降级为 None（可观测故障不阻断业务）。
6. **失败降级**：LangfuseTraceSink 全部方法内部 try/except + WARN 日志——上报失败绝不影响问答。

## 验证口径

- 单测：Settings 默认值（enabled=false/密钥空）；LangfuseTraceSink 用假 langfuse 客户端锁 trace/span/generation 调用序与降级（client 抛错不外泄）；ChatService 假图 + 假汇锁 start_trace→events→end_trace 顺序；LLMService 三路径 generation 记录；with_node_status span 压栈/弹栈/异常路径。
- DDD 守护：langfuse 进 domain/application 禁入名单。
- Smoke：LANGFUSE_ENABLED=false 与 =true（缺密钥）两种配置真实启动均健康。
- 真实 Langfuse 服务端验证待密钥/自托管环境（外部依赖），由用户配置后补验——契约已由假客户端测试锁定。

---

# 四期增强：全量 Prompt 优化（BE-044）

> 依据：2026-09-13 用户要求「优化一下所有的 prompt」。
> 范围：主图 6 + RAG 子图 6 共 12 个 Prompt；行为契约（SSE/grounding 字面锚点/JSON Schema/角色标记词）零变更。

## 硬约束（不可破坏的三方耦合）

1. **角色标记词**（测试脚本化 LLM 按其分流）：意图路由器/顶层编排器/回答校验器/检索规划器/改写器/子查询生成器/扩展器/证据评估器/恢复规划器——必须原样保留在各 system prompt 中。
2. **字面锚点**（BE-017/ADR-0006/grounding 规则档）：answer_generator 的「优先依据」「知识库中暂无相关依据（，建议咨询专业律师）」「禁止」「严禁虚构」；回答须含【来源：…】格式的约定（与 grounding_checker 的 _SOURCE_MARKER 联动）。
3. **JSON 契约**：全部输出键与枚举值域不变（normalized_query/intent/request_type/extracted_conditions；action/reason；use_*/target_evidence；queries；sufficient/confidence/missing_evidence/conflicts/local_recovery_possible/suggested_external_queries；actions/missing_evidence/reason；passed/unsupported_claims/citation_issues/reason）。

## 优化点（12 个 Prompt 统一）

1. **统一五段结构**：角色定位 → 任务与输入说明 → 输出格式（JSON 示例）→ 判定/执行规则（编号）→ 输出纪律。
2. **强化 JSON 输出纪律**：「只输出一个合法 JSON 对象：以 { 开始、以 } 结束，不要 markdown 代码块（如 ```json），不要任何解释文字」——减少容错解析与重试（省 LLM 调用）。
3. **消除示例值锚定偏差**：所有 JSON 示例统一加「示例中的值仅为格式示意，必须按实际情况填写」；evidence_grader 额外强调「宁可判不充分，不可误判充分」（与代码安全默认同向）。
4. **answer_generator 明确来源标注格式**：要求引用处以【来源：文件名】标注并给出格式示例——直接针对 Session 031 记录的"GLM 偶发首答缺【来源：被规则档打回"；同时补"简洁不重复、不堆砌无关条文"约束（E2E 实测回答存在重复句）。
5. **direct_answer 明确避雷**：一般性对话不输出具体法条编号与精确法律数据（会触发校验打回）——针对 Session 033 记录的闲聊被打回 3 次。
6. **grounding 校验器降误判**：RAG 档补「条文转述与来源实质一致即可，不要求逐字匹配」；GENERAL 档补「与法律权威无关的数字（序号、功能数量、日常数字）不算法律数据」——减少 judge 误判导致的重复生成。
7. **量化引导**：retrieval_planner 的 target_evidence 补 1~6 条引导；其余措辞精简，删冗余重复句。

## 验证口径

- 全量 pytest 保持绿（脚本化 Fake 按 9 个标记词分流，锁契约不破）。
- 真实 E2E（GLM）：verify_real_e2e.py 全断言；Langfuse 云端对比 regenerating 次数（优化前 RAG 2 次/闲聊 3 次打回为基线，观察打回是否下降）；闲聊一次通过。
- 前端零改动。
