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
