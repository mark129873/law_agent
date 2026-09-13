# 会话交接

## 当前已验证
- 现在明确可用的部分：
  - **Agent 模块一期重写 + 思考块 + Langfuse trace + 全量 Prompt 优化全部 passing（BE-032~044 + FE-001~016；BE-030 deprecated）**：主图 15 节点 + RAG 子图 10 节点 + 服务层 + status/think 双事件 + 豆包式思考块 + Langfuse 三级追踪 + 12 个 Prompt 五段结构化。
  - **全量 Prompt 优化（BE-044，本轮新增）**：12 个 Prompt 统一五段结构（角色/任务/格式/规则/纪律）+ JSON 纪律（禁 markdown 代码块）+ 示例值防锚定标注 + answer_generator 明确【来源：文件名】格式硬约束 + grounding 降误判（实质一致即可/无关数字不算法律数据/宁可放行）。**编排器"不 finish"误诊修正**（Langfuse 时间线取证：闲聊打回真凶是重复执行 direct_answer，非 judge）——regenerating：RAG 2→0、闲聊 3→0；RAG 回答从 65 字重复堆砌变一句精准+来源标注。
  - **Langfuse trace（BE-043，本轮新增）**：domain TraceSink/TraceSpan 端口 + trace_sink_var（ContextVar）；infrastructure/trace/langfuse_sink.py（langfuse 4.15.2）；ChatService 记 trace 生命周期与流程事件、with_node_status 压/弹节点 span（子图嵌套）、LLMService 三路径记 generation；.env 开关 LANGFUSE_ENABLED（默认 false，缺密钥 WARN 降级，全方法吞异常）。
  - **真实云端验证通过**（jp.cloud.langfuse.com，用户 .env 预置密钥）：E2E trace 含 29 节点 span / 11 generation（model+Prompt+输出）/ 15 think + 2 regenerating 事件。
  - **测试体系**：自动化 225 个（unit 155 含 agent 98 / integration 70 含 agent 12 与 API 9）；test_milvus_vector_store.py 5 例需真实 Milvus（不可达自动跳过）。
- 最近一轮实际跑过的验证（2026-09-13，Session 034 收尾）：
  - 干净环境（删 data + reset_milvus）全量 `uv run pytest tests -q` → **225 passed**（9 角色标记词分流全绿，Prompt 契约零破坏）
  - 真实 E2E（GLM+Milvus）：verify_real_e2e.py 全断言通过，RAG 回答一句精准+【来源】一次通过；闲聊 curl 实测 0 regenerating
  - Langfuse 打回率对比：RAG regenerating 2→0、闲聊 3→0；judge verdict 留档取证（时间线定位编排器重复决策）
  - 验证后已清理：law_chunks 集合 drop、backend/data 删除、后端进程停止

## 本轮改动（Session 038：一期设计稿删除——30 条约束与 § 号速查并入 ARCHITECTURE §12）
- **普查先行**：代码引用 57 个设计 § 号 + 30 处"约束 N"——ARCHITECTURE.md 新增 §12：30 条强制约束逐条保编号收录 + 设计 §号速查表（核心内容 + 权威现落点）
- **删除**：docs/archive/legal_agent_phase1_technical_design.md（git rm）；ARCHITECTURE/agent/__init__ 引用改指 §12；设计 §XX/约束 N 语义自此由 §12 唯一承载
- **上一轮（Session 037，ba871d1）**：全文文档优化——Session 021~030 沉降、设计稿曾入冷存、去重复、补 README
- **上一轮（Session 036，f16a9ed）**：plan.md 悬空引用修复——硬约束清单迁 ARCHITECTURE §11、D1~D12 决策表迁 PRODUCT §6
- **上一轮（Session 033 Langfuse，0a14ca9/8f6e0fb）**：RELIABILITY/ARCHITECTURE + trace_sink 端口 + infrastructure sink + ChatService/包装器/LLMService 采集 + .env 开关
- **后端**：
  - `domain/services/trace_sink.py`：TraceSink/TraceSpan 协议 + trace_sink_var + current_trace_sink()
  - `agent/trace_context.py`：trace_span_var（当前节点 span，LLM generation 挂靠父 span）
  - `infrastructure/trace/langfuse_sink.py`：LangfuseTraceSpan/LangfuseTraceSink/LangfuseTraceSinkFactory（懒初始化、缺密钥 WARN 降级、全方法吞异常、`__call__ = create` 别名）+ null_trace_sink_factory
  - `agent/node_status.py`：包装器增 span 压栈/finally 弹栈（异常也 end，父级恢复）
  - `agent/services/llm_service.py`：invoke/structured_invoke（每次尝试一条）/stream（聚合增量）记 generation；messages 序列化 role 用 .value
  - `application/services/chat_service.py`：构造器增 trace_sink_factory；stream_answer 设/重置 ContextVar、start_trace/end_trace（正常 output/异常 error）、plan/sources/think/regenerating → record_event
  - `containers.py`：_build_trace_sink_factory 按 LANGFUSE_ENABLED 注入
  - `config/settings.py`：langfuse_enabled/base_url/public_key/secret_key
  - 测试：test_trace_sink.py（假客户端 6 例）、test_llm_service_trace.py（8 例）、test_chat_service_trace.py（4 例）、test_node_status 增 3 例、test_settings 增 2 例、DDD 守护加 langfuse
  - 用户 backend/.env：LANGFUSE_ENABLED=true（复用预置密钥与 LANGFUSE_BASE_URL）

## 仍损坏或未验证
- 已知缺陷：无
- 未验证路径：
  - Langfuse 自托管实例未验证（用户用云版；开关口径一致）
  - Ollama LLM 路径真实 E2E、MySQL 8.0、Web Search 二期（既有未验证项）
- 下一轮会话需要注意的风险：
  - **pymilvus load_dotenv 副作用升级**：.env 现含 LANGFUSE_ENABLED=true，会灌入测试进程环境——新增 API/集成测试时必须在 Settings 显式 `langfuse_enabled=False`（test_api 夹具已示范），否则测试触真实观测平台
  - **langfuse v4 查询口径**：验证/导出要用 `api.trace.get(id)` 完整详情或 observations.get_many 带 fields——get_many 裸调不返回 input/output/model，别误判为上报缺失
  - **SDK 后台批量上报**：网络受限时见 export timeout 日志（sink 吞异常不影响业务）；进程退出前如需强推可 `client.flush()`
  - **编排器"不 finish"误诊已修正（BE-044）**：旧记录"judge 对 direct 路径过度敏感"实为编排器重复选 direct_answer（Langfuse 时间线取证）——若回归先查编排决策的 generation 留档（api.trace.get），不要想当然调 judge Prompt
  - **Prompt 修改纪律**：9 个角色标记词（意图路由器/顶层编排器/回答校验器/检索规划器/改写器/子查询生成器/扩展器/证据评估器/恢复规划器）与 BE-017 字面锚点被测试断言，改 Prompt 前先查 tests 的 marker/锚点清单（docs/ARCHITECTURE.md §11「Prompt 与事件硬约束契约」有全列表）
  - 既有风险不变：每问题 LLM 调用 5~8 次；BE-017 字面锚点三方联动
  - **ADR 体系已删除（Session 035）**：注释/文档不得再新增 ADR-XXXX 引用；架构决策统一引用 docs/ARCHITECTURE.md
  - **Windows 端口清理**：停 uvicorn/npm 后子进程可能残留占端口，需 netstat 找 PID + taskkill //F
- 下一步最佳动作（需用户决定）：失败查询链路优化（已量化：最坏 20 次 LLM/24 检索/3 重排；方案=恢复轮经济模式+零新增早退+同能力防重入护栏+预算参数可配）；可选产品增强（会话重命名/停止按钮/CORS 收敛）；MySQL 8.0 接入；Web Search 二期立项
- 这一步中哪些东西不要动：后端 API 契约（§7 SSE）；领域层零技术依赖（langfuse 已入守护名单，只允许 infrastructure/trace）；**trace_sink_var 的注入时机（必须在图任务创建前 set）**；**LangfuseTraceSink 全方法吞异常原则**；双预算常量；BE-017 字面锚点联动

## 命令
- Milvus 启动：`cd backend && docker start milvus-etcd milvus-minio milvus-standalone`
- 后端启动：`cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 干净环境重置（两步）：删除 `backend/data/` + `uv run python scripts/reset_milvus.py`
- 后端验证：`cd backend && uv run pytest tests -q`（全量 225 个；Milvus 未启动时 5 例自动跳过）
- 前端构建/启动：`cd frontend && npm run build` / `npm run dev`
- 端到端：启动服务器后 `PYTHONPATH=backend uv run --with httpx python backend/scripts/verify_real_e2e.py`
- Langfuse 云端查证：`api.trace.list / api.trace.get(id)`（完整详情含 observations IO）
- 图导出：`cd backend && uv run python scripts/export_qa_graph.py`

