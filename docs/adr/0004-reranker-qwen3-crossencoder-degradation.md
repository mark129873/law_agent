# ADR-0004：统一 Rerank 采用本地 Qwen3-Reranker-0.6B（CrossEncoder），失败降级 RRF 序

- 状态：Accepted（2026-09-13）
- 关联：legal_agent_phase1_technical_design.md §32/§34/§47、BE-033、plan.md 决策 D4

## 背景

设计要求 evidence_ranking_node 对多 Query 召回的候选以 original_query 统一重排（约束 18）。用户提供本地模型示例：`Qwen3-Reranker-0.6B` 经 sentence_transformers CrossEncoder 加载（模型已在本地 HF 缓存，快照路径见 backend/scripts/check_rerank_model/check_rerank_local.py），依赖 sentence-transformers/torch 已入 pyproject。

## 决策

1. **模型与加载**：CrossEncoder（LogitScore 打分头）、CPU 推理、**懒加载单例**（首次 rerank 才加载，asyncio.Lock 防并发重复加载）；加载与推理是阻塞调用，经 `asyncio.to_thread` 执行避免卡死事件循环。
2. **依赖倒置**：RerankerService 依赖抽象打分器（`score(query, documents) -> list[float]`），生产实现 CrossEncoderScorer（懒加载适配器），测试注入脚本化打分器——自动化测试不加载真实模型（测试封闭性约束）。
3. **降级路径（设计 §47）**：模型加载失败或推理异常时，保留 Milvus 服务端 RRF 融合序截断返回，`degraded=True` 由 evidence_ranking_node 写入 trace（`reranker_degraded`）——检索主链路永不因 reranker 故障中断。
4. **配置**：`RERANKER_MODEL_PATH` 默认 HF 模型 id，本地部署推荐指向快照绝对路径（离线可用）；`RERANKER_DEVICE` 默认 cpu。重排口径：query=original_query（约束 18），top_n=LegalRAGConfig.rerank_top_k=10（决策 D4）。

## 后果

- 正向：本地部署零 API 成本、离线可用；0.6B 在 CPU 上对 ≤10 条候选的延迟约 1~3s，在可接受范围（用户已确认）。
- 代价：引入 torch 重依赖（venv 体积、启动内存）；模型加载失败只能降级精度——已由 degraded 标记保证可观测。
- 中性：rerank_score 与 rrf_score 并存于 EvidenceItem——排序以 rerank_score 为准，rrf_score 保留作降级序与调参观测。
