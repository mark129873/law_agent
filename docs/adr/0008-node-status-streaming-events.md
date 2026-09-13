# ADR-0008：节点状态流式事件（ContextVar 注入式发射器，Codex 风格前端展示）

- 状态：Accepted（2026-09-13）
- 关联：docs/PRODUCT.md §3、BE-041/FE-015、plan.md 决策 D5

## 背景

用户要求（D5）：后端每个节点的运行状态流式展示在前端（Codex 风格浅色小字）。首选实现是 langgraph 原生 stream writer，但 BE-038 探针实测：langgraph 1.2.11 中**子图节点经 get_stream_writer 推送的 custom 事件不上浮到父图 astream**（`PARENT custom events: []`）——而 plan/sources 事件恰恰产自 legal_rag 子图内部。

## 决策

1. **ContextVar 注入式事件发射器**（app/agent/events.py）：适配器（LangGraphQaWorkflow）在 astream 执行期间把"队列投递函数"放入 ContextVar；所有节点（主图与子图）统一经 `emit_event` 发射。astream 实现 = ainvoke + 队列排空——事件顺序即执行顺序；ainvoke 路径无接收器，事件安全丢弃；消费方提前断开时取消图任务防泄漏。
2. **status 事件契约**（字段只增）：`{"type": "status", "node", "label", "phase": "start|end", "duration_ms"}`；label 用 agent/constants.py 的中文映射表（24 节点全登记，未登记回退节点名）。
3. **建造者层统一包装**：`with_node_status` 包装全部主图 + 子图节点（DRY，节点零改动）——"每个 node 都有状态"由装配机制保证；异常路径也推 end（前端状态行不悬挂）后原样重抛；status 与 trace/日志共用同一计时源。
4. **RAG 子图复合节点显式 I/O**：主图经 `_make_rag_node` 包装子图调用（输入只传 original_query/normalized_query，输出只回写 4 个主图键）——比 langgraph 同名通道匹配更确定，且复合节点自身获得 status 事件。
5. **消费端**：ChatService 增加 status 显式分支（仅转发、不进 delta 聚合——否则状态文本会被拼进回答）；SSE 路由增加 status 帧映射。

## 后果

- 正向：跨子图事件可靠贯通（测试锁定主图 + 子图节点均有 status）；前端零协议破坏（字段只增）。
- 代价：放弃 langgraph 原生 custom 流（其行为随版本变化的风险被隔离在适配器内）；astream 从引擎流改为队列流，多了一层队列。
- 中性：status 事件流量约为节点数的 2 倍/问题（每个节点 start/end 各一帧）——浅色小字展示语义下可接受。
