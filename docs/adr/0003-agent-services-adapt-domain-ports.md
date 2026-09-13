# ADR-0003：Agent 服务层适配领域端口，节点禁止直连底层 SDK

- 状态：Accepted（2026-09-13）
- 关联：legal_agent_phase1_technical_design.md §29/§34/§39、BE-033

## 背景

设计要求 Agent 模块的服务层（services/）统一封装外部依赖，业务节点不散落 SDK 初始化（约束 23/24/25）。项目已有成熟的领域端口：LLMProvider（chat/stream）、EmbeddingService（embed_query）、VectorStore（hybrid_search，Milvus 服务端已完成 Dense+BM25+RRF 融合，BE-029）。

## 决策

1. **MilvusService 不直连 pymilvus SDK**：适配既有 VectorStore 端口——设计 §29 接口中的 dense_top_k/bm25_top_k/rrf_k 属服务端融合细节（RRFRanker(k=60) 已在 MilvusVectorStore 固化），端口契约只暴露融合后 top_k 与稠密通道 min_score，语义等价。
2. **LLMService 适配 LLMProvider**：节点只经 LLMService 调模型（约束 24：不允许节点散落初始化 LLM Client）。结构化输出用 `structured_invoke(messages, schema, default)` 实现——chat + JSON 容错解析（代码块/前后噪声均可）+ 失败重试 1 次（附修正指令）+ 安全默认（Planner 默认 original、Grader 默认 insufficient，设计 §47），不扩展 Provider 端口签名。
3. **CitationService 无状态**：证据条目 → Citation（设计 §41）的纯转换服务。
4. **重型本地推理库隔离**：sentence_transformers/torch/transformers/accelerate 仅允许在 app/agent/ 内导入（reranker 适配器），由 DDD 边界守护测试机械校验（与本条 ADR 同步落地）。

## 后果

- 正向：复用 BE-029 的服务端混合检索与既有 Provider 体系，零重复实现；测试以端口 Fake 替换即可（约束 28），自动化测试不触碰 Milvus/真实模型。
- 代价：MilvusService 不透出两路原始分数（dense/bm25），EvidenceItem 的对应字段一期留空——字段已预留（见 legal_rag/state.py），二期需要时在端口层扩展。
- 中性：结构化输出是"提示工程 + 解析容错"而非模型原生 function calling——与既有 BE-030 判分器同一模式，行为已被验证可靠。
