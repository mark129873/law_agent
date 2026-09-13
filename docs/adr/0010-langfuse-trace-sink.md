# ADR-0010：Langfuse 全链路 trace（ContextVar 注入式可观测汇，.env 开关）

- 状态：Accepted（2026-09-13）
- 关联：docs/RELIABILITY.md、docs/ARCHITECTURE.md §2/§6、BE-043、plan.md 三期增强节、ADR-0008（ContextVar 注入式事件机制——本决策与其同构）

## 背景

用户要求在项目中接入 Langfuse 做 trace，开关作为配置放在 .env 中。项目已有一套进程内可观测（结构化日志 BE-027、节点 trace 通道、status/think SSE 事件 BE-041/042），但都是"看日志/看前端"视角；Langfuse 提供的是跨请求的 LLM 可观测平台（trace → span → generation 层级、Prompt/输出留档、耗时瀑布图）。约束：领域层零技术依赖（守护测试锁死）；应用层禁止直连基础设施；langfuse 是外部 SaaS/自托管服务，必须可一键关闭且故障不得影响问答。

## 决策

1. **领域端口 + ContextVar 注入（与 ADR-0008 同构）**：`domain/services/trace_sink.py` 定义 `TraceSink`/`TraceSpan` 协议与 `trace_sink_var`（stdlib ContextVar）。ChatService 在 `stream_answer` 开始时把**每请求新建**的 sink 放入 ContextVar——图任务经 `asyncio.create_task` 继承（创建发生在 set 之后，happens-before 保证可见）；请求结束重置。禁用/无消费者时为 None，全部上报点廉价跳过（与事件发射器"无消费者安全丢弃"同一语义）。
2. **三级采集，各归其位（不新造机制，全部挂在既有唯一出入口上）**：
   - **trace 生命周期 → ChatService**（应用层，请求唯一编排点）：`start_trace(session_id=conversation_id, input=question)`；plan/think/sources/regenerating 事件经 `record_event` 留档；正常结束 `end_trace(output=完整回答)`、异常 `end_trace(error=...)` 后原样上抛。
   - **节点 span → with_node_status 包装器**（agent 层，"每个节点都有 span"由装配机制保证，DRY）：执行前 `start_span(node, parent=栈顶)` 压入 agent 内部 `trace_span_var`，finally 中 `span.end(duration_ms, error)` 弹出恢复父级——子图复合节点天然形成父子嵌套；异常路径也 end。
   - **LLM generation → LLMService**（agent 层，模型调用唯一入口 BE-033）：invoke / structured_invoke（每次尝试一条，metadata 带 attempt 与 schema 名）/ stream（聚合增量后一条）经当前 span 记 generation（model、messages、output、耗时、错误）。
3. **基础设施实现 + 装配开关**：`infrastructure/trace/langfuse_sink.py` 持有 langfuse 客户端（懒初始化单例）；`containers` 按 `LANGFUSE_ENABLED` 注入工厂——关闭时工厂返回 None（langfuse 模块零导入、零开销）；开启但密钥缺失 → WARN 降级为 None（同类于 BE-027 日志故障不阻断业务）。**LangfuseTraceSink 全部方法内部 try/except + WARN**：可观测上报永远不把业务变成 5xx。
4. **配置**（pydantic-settings，敏感字段只经 .env/环境注入）：`LANGFUSE_ENABLED`（默认 false）、`LANGFUSE_BASE_URL`（默认 https://cloud.langfuse.com）、`LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`。
5. **DDD 守护**：langfuse 加入 domain/application 技术库禁入名单（测试锁死）；实现只存在于 infrastructure。

## 备选与取舍

- **langfuse.langchain CallbackHandler 自动采集**：本项目 LLM 调用是自研 Provider（非 langchain 模型接口），回调挂不上；且自动采集粒度不可控——否，用手工 sink 精确对应三级结构。
- **在 ChatService 消费 status 事件重建节点层级**：事件经队列异步排空，与图任务内的 generation 记录存在跨任务时序竞态（generation 可能先于对应节点 start 事件被处理），嵌套不可靠——否，span 压栈放在图任务内的包装器上，与 generation 同上下文，顺序确定。
- **领域层直接依赖 langfuse SDK**：违反零技术依赖铁律——否，端口 Protocol（零依赖）+ infrastructure 实现（DIP）。
- **trace 输出/输入全量原文**：回答与 Prompt 全文进 Langfuse 是其核心价值（Prompt 留档/回归对比），体量可控（单问 ≤ 数 KB）——接受；思考内容已在上游截断 120 字。

## 后果

- 正向：Langfuse 中每问一条 trace——节点瀑布（含子图嵌套）、每次 LLM 调用的 Prompt/输出/耗时/重试、检索策略与思考内容留档；开关一键关闭回归纯本地运行；三级结构与代码三级出入口一一对应（可测试性好）。
- 代价：agent 层包装器与 LLMService 增加上报调用（None 时近零开销）；启用时每问题多若干次本地内存操作 + SDK 后台批量上报（网络故障被 SDK 缓冲与 sink 降级吸收）。
- 中性：真实 Langfuse 服务端验证依赖外部环境（云账号密钥或自托管 compose），本轮以假客户端测试锁契约 + 降级 smoke；真实联通为待补验证项。
