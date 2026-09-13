# ADR-0002：SSE 对外契约向后兼容，CapabilityResult 为图内部统一结构

- 状态：Accepted（2026-09-13）
- 关联：docs/ARCHITECTURE.md §7、docs/PRODUCT.md §3/§4、BE-038、BE-041

## 背景

Agent 模块整体重写，但 ChatService、前端与持久化契约不应随之重写。对外唯一问答入口是 SSE 流式接口，前端按事件类型渲染（流式增量、参考文档、检索策略、工作过程展示）。

## 决策

1. **QaWorkflow 领域端口不变**：`ainvoke`/`astream` 签名、`{"question","history"}` 输入与 `answer` 输出键保持；新图经适配器实现同一端口，ChatService 与装配点的耦合面最小化（仅 create_qa_workflow 工厂签名更新）。
2. **SSE 事件字段只增不改**：既有 plan/sources/delta/regenerating/done/error 形状不变；本期新增：
   - `plan.sub_queries` 语义扩展为"全部检索查询"（检索策略展示，D1）——字段名不变，内容语义变化已同步 PRODUCT.md；
   - 新增 `status` 事件（node/label/phase/duration_ms，节点运行状态展示，D5）。
   旧前端对新字段/新事件静默忽略，不破坏兼容。
3. **CapabilityResult 是图内部统一结构**（capability/status/content/evidence/citations/metadata）：所有 Capability（RAG 子图、Web Stub、Plugin Stub、直接回答）经 observation_node 归一为该结构后再进主循环；不外泄到 SSE 协议——对外事件与内部结构的映射只发生在图节点与 ChatService。
4. **用户可见行为变更先行 PRODUCT.md**：检索策略全量展示、直接回答路径、状态过程展示、参考文档 10 条上限、证据不足展示规则，均已先于实现写入 PRODUCT.md §3/§4。

## 后果

- 正向：前端与 API 契约零破坏；重写只影响 app/agent/ 内部；测试可用"过滤 status 后保持原序"校验既有序列。
- 代价：ChatService 需为 status 事件增加显式转发分支（当前 else 分支会把未知事件当增量拼接，属必须修复点）。
- 中性：`plan.sub_queries` 内容语义变化对旧前端只是"列表更长"，无渲染风险。
