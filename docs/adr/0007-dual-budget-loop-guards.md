# ADR-0007：双预算防死循环（主图 max_global_steps / RAG 恢复 max_retries）

- 状态：Accepted（2026-09-13）
- 关联：legal_agent_phase1_technical_design.md §12/§37/§46、BE-035/BE-036

## 背景

新架构存在两类循环：主图 orchestrator↔observation 顶层循环与 grounding 打回回路；RAG 子图的 evidence_grader↔recovery_planner↔strategy_router 恢复循环。LangGraph 条件回边若无预算约束，任何判定抖动都会死循环（项目在 BE-030 已踩过"空命中无限重规划"的坑）。

## 决策

1. **两套预算相互独立**（设计 §2.4）：主图 `max_global_steps=4`（顶层编排与 grounding 打回共用此预算），RAG 子图 `max_retries=2`（恢复循环专用，一期不超过 3）。
2. **预算检查位置在条件边**：恢复循环的预算判定在 `route_after_evidence_grade`（retry_count < max_retries），主图 grounding 打回预算在 grounding_checker 的条件边（global_step_count < max_global_steps）——"怎么补救"归节点，"还要不要补救"归路由。
3. **主图侧双保险**：orchestrator_agent 在 global_step_count 达上限时无视 LLM 输出强制 finish——条件边是第一道闸，节点内是第二道。
4. **超预算的行为语义**：恢复循环耗尽 → 带已有证据输出 LOCAL_EVIDENCE_INSUFFICIENT（不伪装成功）；grounding 预算耗尽 → fallback_generator_agent 输出谨慎回答（不输出未校验的草稿）。

## 后果

- 正向：任何 LLM 判定抖动最多消耗有限步数；两条循环互不挤占预算——RAG 内部多轮恢复不会吃掉主图编排预算。
- 代价：极端场景下回答质量受预算限制（宁可谨慎回答也不无限重试）——已由 fallback 与"信息不足"策略兜底。
- 中性：预算常量是防死循环的正确性边界（与 BE-030 的 MAX_PLAN_RUNS 同性质），调整属行为变更需走测试。
