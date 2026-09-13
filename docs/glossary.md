# Glossary — Agent 一期术语表

> 一期重写（BE-032~041）引入的领域术语速查。设计依据 legal_agent_phase1_technical_design.md，
> 决策依据 docs/adr/0001~0008。

## 图结构

| 术语 | 含义 |
|------|------|
| 主图（Main Graph） | 顶层 LangGraph 图：意图路由 → 编排循环 → Capability 分派 → 回答收尾链（agent/graph.py） |
| Local Legal RAG 子图 | 独立编译的检索子图（agent/subgraphs/legal_rag/），作为主图复合节点接入；只做本地检索，禁触 Web/Plugin |
| Capability | 主图可调度的能力单元：local_legal_rag / web_search / plugin / direct_answer，统一输出 CapabilityResult |
| CapabilityResult | 能力统一结果结构：capability/status/content/evidence/citations/metadata（设计 §10）；observation_node 据此归一 |
| `_agent` / `_node` | 节点命名规则：带 LLM 的节点以 `_agent` 结尾，确定性节点以 `_node` 结尾（设计 §2.1） |

## 查询与检索

| 术语 | 含义 |
|------|------|
| Retrieval Plan | 检索计划（retrieval_planner_agent 产出）：四类策略**多选**开关 + 目标证据主题 |
| 查询变体（Query Variants） | original（原始）/ rewrite（改写 ≤2）/ subquery（子问题拆分 ≤5）/ expansion（术语扩展 ≤3） |
| fan-out | strategy_router_node 条件边返回目标列表，多个变体节点并发生成（约束 15/17）；各写独立 state 键防并发冲突 |
| retrieval_queries | 一轮实际检索的查询列表：四类合并 → 归一化去重 → 排除已检索 → 截断 ≤8（设计 §26） |
| Hybrid Retrieval | 单查询 Dense + BM25 + RRF 由 Milvus 服务端一次 hybrid_search 完成（BE-029）；多查询 asyncio.gather 并发 |
| Recovery Loop | 证据不足时的本地恢复循环：recovery_planner → strategy_router → 变体节点 → 检索，受 `max_retries=2` 预算 |
| LOCAL_EVIDENCE_INSUFFICIENT | 子图结论"本地证据不足"：已有证据照常返回（谨慎回答用），并透传 missing_evidence / suggested_external_queries |

## 证据与引用

| 术语 | 含义 |
|------|------|
| EvidenceItem | 证据条目：chunk 溯源字段 + query/query_type + rrf_score/rerank_score + matched_queries（设计 §7） |
| 去重三级键 | chunk_id > (document_id + chunk_index) > content_hash；多 Query 命中合并 matched_queries（设计 §33） |
| 统一 Rerank | 以 original_query（非子查询）对候选重排（约束 18）；Qwen3-Reranker-0.6B CrossEncoder，失败/关闭降级 RRF 序（ADR-0004） |
| 粗排→精排 | rerank 前按 RRF 分预截断 `rerank_max_candidates=20`（CPU 0.6B 实测约 15s/对的可行性边界） |
| rerank_top_k | 精排保留条数（10）：进入回答上下文与「参考文档」展示（决策 D4） |
| Citation | 引用条目（设计 §41）：citation_id 按证据顺序编号，final_answer_node 生成 |

## 校验与预算

| 术语 | 含义 |
|------|------|
| Grounding | 回答依据校验：Claim↔Evidence / Citation↔Source；规则档（来源标注/信息不足声明）先行 + LLM judge 档 |
| grounding 双规则 | 检索路径：有依据必须【来源：…】、无命中必须声明信息不足；直接回答路径：只查编造法条/案例（ADR-0006） |
| 直接回答路径 | 一般性对话（问候/概念/系统说明）跳过检索直接流式回答（决策 D2）；direct_answer_agent 是其唯一流式出口 |
| max_global_steps | 主图预算（4）：编排与 grounding 打回共用；orchestrator 超限强制 finish，grounding 每次执行 +1（ADR-0007） |
| max_retries | RAG 恢复循环预算（2）：route_after_evidence_grade 条件边检查 |
| Fallback | grounding 预算耗尽后的谨慎回答（fallback_generator_agent）：只陈述有依据内容 + 明示不确定 |

## 事件与可观测

| 术语 | 含义 |
|------|------|
| QaStreamEvent | 领域流式事件值对象：delta / sources / plan / regenerating / status（字段只增，ADR-0002） |
| status 事件 | 节点执行状态（BE-041/D5）：node + 中文 label + phase(start/end) + duration_ms；前端浅色小字过程展示 |
| emit_event | ContextVar 注入式事件发射（ADR-0008）：跨子图贯通、图外安全丢弃；因 langgraph 1.2.11 子图 custom 事件不上浮而生 |
| with_node_status | 建造者层节点包装：起止 status + 结构化日志；"每个节点都有状态"由装配机制保证 |
| plan 事件语义 | 携带**全部检索查询**（非仅子问题）：前端「检索策略（N 条查询）」展示（决策 D1） |
| rag_trace | 子图内部 trace（operator.add 归约器），独立命名避免与主图 trace 通道互相覆盖 |
| trace | 节点执行记录（设计 §48）：node/status/duration_ms + 业务计数；主图 trace 通道为追加归约器 |
| think 事件 | 节点内打印的思考内容行（BE-042/D9）：node + label + text（后端 `truncate_text(120)` 截断保证；JSON 决策拼句后打印）；与 status 互补——status 表节点起止，think 表过程内容（ADR-0009） |
| 思考块（Thinking Panel） | 前端统一过程容器（FE-016/D6）：聚合 status 行 + plan 检索策略 + think 内容行；生成中默认展开，完成后自动收起为「已完成思考 · Ns」一行（D7），点击切换；仅内存快照，刷新不保留（D10），出错保留（D12） |
| TraceSink | 可观测汇领域端口（BE-043/ADR-0010）：TraceSink/TraceSpan 协议 + trace_sink_var（ContextVar 注入，与 ADR-0008 同构）；ChatService 记 trace 生命周期与流程事件、with_node_status 压/弹节点 span、LLMService 记 generation——禁用时为 None 零开销 |
| Langfuse trace | 三级层级（trace→节点 span→LLM generation）：session_id=conversation_id，input=问题，output=完整回答；plan/think/sources/regenerating 留为 trace 事件；langfuse SDK 锁在 infrastructure/trace/，开关 LANGFUSE_ENABLED（缺密钥 WARN 降级） |
