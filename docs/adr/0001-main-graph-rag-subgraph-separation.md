# ADR-0001：主图轻量编排 + 独立 Local Legal RAG 子图 + Web/Plugin Stub 入口

- 状态：Accepted（2026-09-13）
- 关联：legal_agent_phase1_technical_design.md §1~§3、BE-032~BE-038

## 背景

原 Agent 为 BE-030 四节点闭环（plan→retrieve→generate→verify），规划、检索、校验耦合在单一图中。一期重写要求：本地法律 RAG 做到"独立、高质量、可恢复、可验证"，Web Search 与 Plugin/Skill 一期不实现但必须提前固定扩展入口，避免二期替换时重构主图。

## 决策

1. **主图只承担轻量调度与最终回答**：query_router_agent（意图识别）→ orchestrator_agent（下一步 Capability 决策，受 max_global_steps=4 预算）→ action_router_node（确定性路由）→ Capability → observation_node（统一结果合并）回环；finish 后 answer_generator → grounding_checker → final_answer / fallback。
2. **Local Legal RAG 独立为 Subgraph**（agent/subgraphs/legal_rag/）：只负责本地检索全链路（检索规划、查询变体、混合检索、重排、证据评估、本地恢复循环），不得调用 Web/Plugin/MCP；作为单个节点接入主图。
3. **Web/Plugin 本期仅保留入口 Stub**：web_search_entry/stub、plugin_entry/stub 节点只返回 NOT_IMPLEMENTED / DISABLED，禁止实际联网或动态加载外部代码；二期替换 Stub 内部实现，主图路由接口不变。
4. **两套独立预算**：主循环 max_global_steps=4、RAG 恢复循环 max_retries=2，互不挤占，防死循环。

## 后果

- 正向：RAG 子图可独立测试与复用；扩展边界提前固定（二期替换 Stub 不动主图）；职责边界与设计文档 30 条强制约束一一对应。
- 代价：节点数量增多（主图 9 + 子图 10 + Stub 4），每问题 LLM 调用次数上升（用户已确认接受，D3）。
- 中性：CapabilityResult 成为所有 Capability 的统一输出结构（图内部契约），SSE 对外协议不变（见 ADR-0002）。
