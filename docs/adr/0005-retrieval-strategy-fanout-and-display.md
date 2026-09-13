# ADR-0005：检索查询四类变体与「检索策略」展示语义

- 状态：Accepted（2026-09-13）
- 关联：legal_agent_phase1_technical_design.md §21~§28、plan.md 决策 D1、BE-034/BE-038

## 背景

一期 RAG 的查询变体有四类：原始问题（original）、改写（rewrite）、子问题拆分（subquery）、术语扩展（expansion），合计上限 8 条。旧版 plan 事件只带 1~3 个子查询。用户决策 D1：plan 事件携带**全部检索查询**，前端文案改「检索策略（N 条查询）」。

## 决策

1. **fan-out 并行生成**：strategy_router_node 的条件边返回目标列表，选中的变体节点并发生成（LangGraph fan-out）；各变体只写独立 state 键（rewritten_queries/sub_queries/expanded_queries，配 operator.add 归约器防并行写冲突），最终汇入 hybrid_retriever_node——所有子查询进同一混合检索（约束 16/17）。
2. **查询汇总发生在 hybrid_retriever_node**：按 original→rewrite→subquery→expansion 固定顺序合并、按归一化文本去重、排除已检索文本（恢复轮）、截断 max_retrieval_queries=8；plan 事件在此推送（此时查询列表已齐且即将执行，语义最准），每轮一次，重规划后覆盖。
3. **恢复轮不再检索原始问题**：recovery plan 归一化时 use_original_query=False，配合 retrieved_query_texts 排除已检索查询——避免重复执行同样失败的策略（设计 §36）。
4. **变体是增强不是必需**：任一变体节点解析失败安全默认为空列表，原始查询始终在队列中，检索流程不因变体故障中断。

## 后果

- 正向：检索策略对用户完全透明（D1）；fan-out 并行使变体生成延迟 ≈ 最慢一个变体而非累加。
- 代价：前端展示条数从 1~3 增至最多 8（文案已改，PRODUCT.md 同步）。
- 中性：plan 事件字段形状不变（sub_queries 数组），仅内容语义扩展——SSE 契约仍向后兼容（ADR-0002）。
