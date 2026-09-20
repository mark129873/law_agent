# progress-archive-031-040（Session 031~040 冷分卷，沉降后只读不改）

> 沉降自 progress.md 热层（2026-09-18，Session 046 执行；触发条件：热层 Session 数 > 15）。内容整条原样搬运，未精简。

### Session 040（GitHub 发布版 README）
- 日期：2026-09-14
- 本轮目标：为仓库提供适合 GitHub 项目首页的中文 README，仅陈述当前代码与文档已经实现或明确标注的能力。
- 改动：重写 `README.md`，补齐项目定位、技术亮点、两张 Mermaid 架构图、RAG/SSE 说明、真实仓库克隆地址、跨平台启动步骤、配置/API/目录结构、验证方式、已知边界、贡献说明与 License 状态；明确 Web/Plugin 仍为 Stub、MySQL 尚未接入以及法律免责声明。
- 验证：逐项对照 `docs/ARCHITECTURE.md`、`docs/PRODUCT.md`、代码配置和 API 路由；本地链接 5 个均有效、2 个 Mermaid 代码块闭合；Milvus 集合重置后全量 pytest `225 passed, 1 warning`，前端 `npm run build` 通过，`git diff --check` 通过。
- 状态：纯发布文档改进，不新增产品功能，`feature_list.json` 状态与证据无需变更；热层 Session 10 个、passing 条目 36 个，均未触发冷热沉降。

### Session 039（收紧失败路径重试预算）
- 日期：2026-09-14
- 本轮目标：按用户要求减少 RAG 无对应文档时的恢复次数，以及主图总体重试预算；不改变架构、节点或 LangGraph 连线。
- 改动：`LegalRAGConfig.max_retries` 从 2 调为 1；`AgentConfig.max_global_steps` 从 4 调为 2；同步 ARCHITECTURE、集成/单元测试和功能证据。
- 验证：相关测试 22 passed；全量 `uv run pytest tests -q -rs` 为 225 passed、1 warning；`npm run build` 通过；`git diff --check` 通过。
- 保持不变：Milvus 单查询异常重试 1 次、LLM 结构化输出解析重试 1 次；`max_global_steps=2` 下 grounding 失败会更快进入现有 fallback。


### Session 038（设计稿删除：核心约束并入 ARCHITECTURE §12）
- 日期：2026-09-14
- 本轮目标：应用户要求把 docs/archive/legal_agent_phase1_technical_design.md（2699 行）最核心内容按需并入 ARCHITECTURE.md 后删除该稿
- 技术决策：删除前先普查代码引用——57 个不同设计 § 号（最高频 §47 错误处理 16 次）+ 约束 3~25 共 30 处"约束 N"引用；据此 ARCHITECTURE.md 新增 **§12「一期设计约束与 § 号速查」**：①原 §53 的 30 条强制实现约束逐条保编号收录（代码按约束号引用，编号不可变）；②设计 §号速查表（仅收录被引用章节，每行核心内容一句话 + 权威现落点：实现文件或本文档小节）；§52 实现顺序/未引用章节不收录
- 运行过的验证：grep 全仓库设计稿引用仅剩 3 处有意保留（§12 标题出处说明 + feature_list/progress 各 1 处历史记录）；本轮纯文档+1 行注释改动，测试沿用 Session 034 基线（225）
- 已记录证据：本轮为文档迁移，feature_list.json 无功能状态变化；设计稿自此无落地文件，"设计 §XX/约束 N"语义由 ARCHITECTURE §12 唯一承载
- 已知风险或未解决问题：无新增
- 下一步最佳动作：失败查询链路优化（方案已备）；OllamaProvider 重试/降级（Session 028 遗留）

### Session 037（全文文档优化：冷热沉降 + 设计稿入冷存 + 去重复 + 补 README）
- 日期：2026-09-14
- 本轮目标：应用户要求"对全文文档优化，保留核心信息、去除冗余信息"
- 做了什么：
  - **沉降（规则强制，Session 数 17>15）**：Session 021~030 整体搬入 docs/archive/progress-archive-021-030.md（行切割保证逐字不差，整条原样）；progress.md 356→116 行，热层归档指针同步，热层 Session 数 6
  - **一期设计稿（2699 行）移入 docs/archive/**（git mv 保留历史）：as-built 已由 ARCHITECTURE.md 承载，但代码注释按"设计 §XX"引用故不删；ARCHITECTURE/agent/__init__ 两处"设计依据"引用补全路径
  - **ARCHITECTURE.md 去重复**：§0 三条技术栈 bullet 与 §1 末尾详细栈合并；§2 目录树 database 长注释压缩（细节归 §3）；§9 测试表/§11 契约清单/§5 mermaid 图（用户明确要求固化）全部保留
  - **RELIABILITY.md**：埋点示例块与级别表语义重复，压缩为一段（埋点清单语义零丢失）；121→108 行
  - **README.md 原为空文件**：补 33 行极简版（简介 + 快速启动 + 文档索引）
- 运行过的验证：冷分卷序号连续（001-010/011-020/021-030）；grep 设计稿引用无悬空；热层文档总量 3804→883 行；本轮纯文档改动，测试沿用 Session 034 基线（225）
- 已记录证据：本轮为文档优化，feature_list.json 无功能状态变化；对账：Session 总数 36 = 热 6 + 冷 30
- 已知风险或未解决问题：无新增（既有：失败查询链路优化待立项、OllamaProvider 重试遗留）
- 下一步最佳动作：失败查询链路优化（方案已备）；OllamaProvider 重试/降级（Session 028 遗留）

### Session 036（文档修复：plan.md 悬空引用清理 + 契约/决策归档）
- 日期：2026-09-14
- 本轮目标：plan.md 被删除后（ce56bf8）遗留两类问题修复——①progress/session-handoff/feature_list 共 6 处 "详见 plan.md" 死指针；②plan.md 承载的三类内容无归档去处（BE-044 硬约束清单、D1~D12 决策表、Langfuse 设计摘要）
- 技术决策：
  - 只增小节不新增文件：**ARCHITECTURE.md 新增 §11「Prompt 与事件硬约束契约」**（9 角色标记词全列表 + 字面锚点 + JSON 契约键值域 + BE-044 优化要点 + think 节点→内容清单，注明为唯一权威清单）；**PRODUCT.md 新增 §6「已确认的产品决策记录（D1~D12）」**（决策留档防实现漂移）
  - Langfuse 设计摘要经逐条比对确认 RELIABILITY.md「Langfuse 链路追踪」节已完整承载，不重复新增，引用改指该处
- 运行过的验证：grep 热层文件 plan.md 引用仅剩 §11 标题中的出处说明（有意保留）；feature_list.json JSON 校验通过；本轮纯文档改动，测试沿用 Session 034 基线（225）
- 已记录证据：本轮为文档修复，feature_list.json 无功能状态变化
- 已知风险或未解决问题：**热层 Session 数 17 > 15，冷热分层沉降条件已触发待执行**（按规则沉 10 个最旧 Session 到 docs/archive/progress-archive-021-030.md，passing 条目 36+4 未超 40 暂不触发 feature_list 沉降）
- 下一步最佳动作：执行 Session 沉降；失败查询链路优化（方案已备）；OllamaProvider 重试/降级（Session 028 遗留）

### Session 035（文档清理：删除 ADR 目录与 glossary 术语表 + 全量引用清理）
- 日期：2026-09-14
- 本轮目标：应用户要求删除 docs/adr/（0001~0010，工作区先前已删未提交）与 docs/glossary.md，并全量清理仓库内引用（用户确认删除是有意的文档重组；ADR 承载的设计实质——双预算、SSE 契约、事件机制、grounding 双规则等——已由 docs/ARCHITECTURE.md 完整承载）
- 做了什么：手动逐处清理 34 个文件——文档层 6 个（ARCHITECTURE/RELIABILITY/plan/progress/session-handoff/feature_list.json，失效路径指针改指 docs/ARCHITECTURE.md）+ 后端源码 20 个 + 测试 7 个 + backend/.env.example；"ADR-XXXX" 标签全量剥离，解释性正文（为什么这么做）一律保留；冷分卷 docs/archive/ 确认无引用，按只读约定未动
- 运行过的验证：
  - grep 全仓库（排除 archive/.git/.venv/node_modules）ADR/glossary 引用 = 0
  - feature_list.json JSON 语法校验通过（node JSON.parse）
  - **测试按用户指示本轮跳过**（纯文档/注释改动，未触任何运行时逻辑与断言；上一基线 2026-09-13 Session 034：225 passed）
- 已记录证据：本轮为文档清理，feature_list.json 无功能状态变化（仅 description 与 BE-040/BE-033/BE-036/BE-043 条目内的引用文本清理）
- 已知风险或未解决问题：ADR 编号自此无落地文件（git 历史提交信息中的 ADR 引用随历史保留）；后续文档/注释不得再新增 ADR-XXXX 引用
- 下一步最佳动作：失败查询链路优化（本轮已完成量化评估未实施：最坏路径 20 次 LLM 调用/24 次 Milvus 检索/3 次重排，正常成功查询约 9 次 LLM；候选方案=恢复轮经济模式+零新增早退+同能力防重入护栏+预算参数 .env 可配）；或既有可选产品增强/MySQL/Web Search

### Session 034（BE-044 全量 Prompt 优化：12 个 Prompt 五段结构化 + 编排器"不 finish"误诊修正）
- 日期：2026-09-13
- 本轮目标：应用户要求优化全部 Prompt（主图 6 + RAG 子图 6）。硬约束：9 个角色标记词（测试脚本化 Fake 分流依赖）、BE-017 字面锚点（优先依据/知识库中暂无相关依据/禁止/严禁虚构/【来源：）、JSON 键与值域零变更
- 技术决策（Prompt 硬约束契约全列表见 docs/ARCHITECTURE.md §11）：
  - **统一五段结构**：角色 → 任务 → 输出格式 → 规则 → 纪律；JSON 纪律升级为"以 { 开始以 } 结束、禁 markdown 代码块"（减少容错解析重试）；所有 JSON 示例加"值仅为格式示意"（消除锚定偏差，evidence_grader 的 sufficient:true 示例曾与代码安全默认反向）
  - **answer_generator**：明确【来源：文件名】格式硬约束+示例（grounding 规则档按该字面检查，此前只说"注明来源文件"致 GLM 偶发漏写被打回）；补"简洁不重复、不堆砌无关条文"（E2E 实测回答有重复句）
  - **grounding 校验器降误判**：RAG 档补"实质一致即可不要求逐字匹配"+"信息不足声明判通过"；GENERAL 档补"无关数字不算法律数据"+"宁可放行不可误杀"
  - **direct_answer 避雷**：禁输出法条编号与精确法律数据（会触发校验）
  - **重大误诊修正（Langfuse trace 取证）**：旧记录"闲聊被 judge 打回 3 次、judge 对 direct 路径过度敏感"是**误诊**——时间线显示真凶是编排器在 direct 已有结果后仍反复选 direct_answer 而非 finish，direct_answer 因 answer_draft 非空发 regenerating（think 文案又误标为"未通过校验"）。修复：编排器规则 3 改为"【最近能力】已执行且无校验反馈 → finish（严禁重复执行已完成的能力）"；direct think 文案改为与真实触发一致
- 运行过的验证：
  - 干净环境全量 pytest **225 passed**（脚本化 Fake 按 9 个标记词分流全绿——契约零破坏）
  - 真实 E2E（GLM+Milvus+Langfuse）：verify_real_e2e.py 全断言通过，RAG 回答从优化前 65 字重复堆砌变为一句精准 +【来源：中华人民共和国专利法.txt】一次通过；闲聊 curl 实测
  - **Langfuse 打回率对比**：RAG regenerating 2→0；闲聊 regenerating 3→0（编排器修复后）；judge verdict 留档确认
  - 验证后已清理：law_chunks 集合 drop、backend/data 删除、后端进程停止
- 已记录证据：feature_list.json BE-044（passing）；对账 60=40 热层（36 passing+4 deprecated）+20 archived
- 已知风险或未解决问题：无新增（既有：RERANK 关闭、Ollama 路径 E2E 未跑、MySQL/Web Search 未接入）
- 下一步最佳动作：可选产品增强（会话重命名/停止按钮/CORS 收敛）、MySQL 8.0 接入、或 Web Search 二期

### Session 033（BE-043 Langfuse 全链路 trace：文档先行 → 实现 → 真实云端验证）
- 日期：2026-09-13
- 本轮目标：应用户要求接入 Langfuse 做 trace，开关作为配置放 .env 中（文档先行，随后实现与真实云端验证）
- 技术决策（Langfuse 设计决策见 docs/RELIABILITY.md「Langfuse 链路追踪」节）：
  - **可观测汇走领域端口**：domain/services/trace_sink.py 定义 TraceSink/TraceSpan 协议 + trace_sink_var（ContextVar，与既有事件机制同构）；langfuse 4.15.2 锁在 infrastructure/trace/（DDD 守护名单加 langfuse，domain/application 禁入）
  - **三级采集各归其位**：trace 生命周期（start/end + plan/think/sources/regenerating 事件）归 ChatService（应用层唯一全景点）；节点 span 归 with_node_status 包装器（start_span 压栈/finally end 弹栈，子图复合节点天然父子嵌套，异常也 end）；LLM generation 归 LLMService（invoke/structured_invoke 含重试轮次/stream 三路径全覆盖，generation 挂当前节点 span）
  - **配置与降级**：Settings 增 LANGFUSE_ENABLED（默认 false）/LANGFUSE_BASE_URL（命名与用户 .env 预置及 SDK 口径一致）/LANGFUSE_PUBLIC_KEY/SECRET_KEY；关闭=工厂 None 零导入零开销；开启但缺密钥=WARN 降级恒 None；sink 全方法吞异常 WARN（可观测故障不阻断业务）
  - **踩坑记录**：①工厂实例注入但 ChatService 按可调用对象调用 → 工厂加 `__call__ = create` 别名；②pymilvus load_dotenv 把 .env 的 LANGFUSE_ENABLED=true 灌进测试环境 → test_api 夹具显式 `langfuse_enabled=False` 隔离；③langfuse v2 observations 查询 API 不带 fields 不返回 IO 字段——**数据其实一直在云端**，验证要用 trace.get 完整详情
- 运行过的验证：
  - 文档先行提交（0a14ca9）后实现；干净环境全量 pytest **225 passed**（+22 例：假客户端锁 sink 契约与降级、ChatService 生命周期序、LLMService 三路径 generation、包装器 span 压弹栈、Settings 默认值/开关、DDD 守护）
  - **真实 Langfuse 云端验证通过**（用户 .env 预置密钥，jp.cloud.langfuse.com，server v4.35.0）：服务启用启动健康 → verify_real_e2e.py 全断言通过（回答引用第四十二条）→ 云端查询确认：1 条 trace（name=chat，input=问题原文，output=完整回答）、29 个节点 span（主图编排循环 + RAG 子图嵌套）、11 个 generation（model=glm-4.5-air，含 Prompt 消息与输出，metadata 带 attempt/schema/duration_ms）、15 条 flow:think + 2 条 flow:regenerating（本轮真实触发 2 次校验打回）
  - 验证后已清理：law_chunks 集合 drop、backend/data 删除、后端进程停止
- 已记录证据：feature_list.json BE-043（passing）；对账 59=39 热层（35 passing+4 deprecated）+20 archived
- 已知风险或未解决问题：
  - Langfuse SDK 后台批量上报（OTel exporter）：沙箱内曾见 export timeout 日志（网络受限场景），不影响业务（sink 吞异常）；网络通畅时无感
  - session 归组目前放在 trace metadata（session_id 字段），未用 SDK propagate_attributes 跨任务传播——Langfuse UI 的 Sessions 视图暂不聚合，属可选增强
  - 自托管 Langfuse 未验证（用户用云版）；MySQL/Web Search 等既有未验证项不变
- 下一步最佳动作：可选产品增强（会话重命名/停止按钮/CORS 收敛）、MySQL 8.0 接入、或 Web Search 二期

### Session 032（全面测试基线 + 思考块 BE-042/FE-016：全面测试→用户样式反馈→当日实现与验证）
- 日期：2026-09-13
- 本轮目标：①按开工流程做全面测试（干净环境全量 pytest/前端 build/真实启动 smoke/真实 E2E）；②用户在浏览器看到 FE-015 平铺状态行后反馈"思考的样式不对，要豆包式可点开收起"→ 按 grilling 定稿（D6~D12）实现思考块并验证
- 技术决策（决策 D6~D12 见 docs/PRODUCT.md §6）：
  - think 事件：QaStreamEvent 扩展 type=think（node/label/text），text 后端 `truncate_text(120)` 统一截断（契约生产端保证）；`emit_think` 统一发射（label 复用 NODE_LABELS，DRY）
  - 13 个节点接入：意图判定/编排决策（JSON 拼句）/选中检索与恢复策略/并发检索命中数/重排降级/证据评估结论/恢复计划/校验判定+理由（_verdict 统一出口）/兜底与重写流转（regenerating 同源）/Web+Plugin 未开通说明/引用来源条数
  - 前端思考块（豆包式）：标题行「思考中…/已完成思考 · Ns」+ 箭头点击切换；manualOpen=null 跟随默认（生成中展开、完成自动收起，消息 id 换名触发重挂载实现自动收起）；AppContext nodeStatuses 升级为 ThoughtLine 统一列表（status 按节点合并 + think 追加）；检索策略面板并入思考块；出错保留思考快照（D12，onError 不再清空并给半截消息挂快照+固定 id）；闲聊同展示（D11）
- 运行过的验证：
  - 全面测试基线（实现前）：干净环境（data 不存在+reset_milvus）197 passed；前端 build 通过；真实启动 smoke（health/空列表/日志初始化序列含 BE-026 自愈）；真实 E2E 全断言通过（201 ready/plan 检索策略/16 节点 status/引用第四十二条/sources 持久化一致）；浏览器 RAG 路径 + grounding 打回→兜底路径真实触发
  - 实现后：干净环境 203 passed（+6 例 think 单测：截断规则/契约拼装）；前端 build 通过；浏览器实操：RAG 生成中思考块默认展开（思考中…+意图判定/编排决策/选中检索策略/命中数实时滚动）→完成后自动收起「已完成思考 · 45.8s」→点击展开显示恢复循环全程（改写/拆解/扩展+校验打回理由+预算耗尽+兜底触发）→点击收回；闲聊路径思考块 10.6s 独立保留；截图确认左线缩进浅色样式
  - 验证后已清理：law_chunks 集合 drop、backend/data 删除、前后端进程停止（vite 残留子进程 taskkill 清理）
- 已记录证据：feature_list.json BE-042/FE-016（passing）；对账 58=38 热层（34 passing+4 deprecated）+20 archived
- 已知风险或未解决问题：
  - grounding judge 模型方差新增观察：闲聊"你能做什么"的能力介绍回答被 direct 规则档打回 3 次才通过（对"不得编造法条"过度敏感），预算耗尽强制收尾兜住——最终行为正确但 LLM 调用增多，建议后续调 direct 路径 judge Prompt 措辞
  - IAB 自动化点击在该标签页系统性超时（fill/evaluate 正常），用 evaluate 程序化点击走 React 合成事件完成验证——自动化工具性问题，非产品缺陷
  - 既有风险不变：每问题 LLM 调用 5~8 次；RERANK_ENABLED=false 降级；Ollama 真实 E2E 未跑
- 下一步最佳动作：可选产品增强（会话重命名/停止按钮/CORS 收敛）、MySQL 8.0 接入、或 Web Search 二期（替换 Stub 即可）

### Session 031（一期 Agent 模块重写：BE-032~041 + FE-014/015 + BE-040 全部落地）
- 日期：2026-09-13
- 本轮目标：按 legal_agent_phase1_technical_design.md 对 agent 模块整体重写（主图 + 独立 Local Legal RAG 子图 + Web/Plugin Stub + 服务层），并按用户决策 D1~D5 实现检索策略全量展示、直接回答路径、节点状态流式展示（Codex 风格浅色小字）、rerank top-10
- 技术决策（产品决策 D1~D5 见 docs/PRODUCT.md §6）：
  - 主图 15 节点（意图路由/编排/动作路由/RAG 子图/Web+Plugin Stub/观察/直接回答/回答生成/grounding/兜底/收尾）+ 子图 10 节点（检索规划/策略路由/三查询变体/并发混合检索/证据重排/评估/恢复规划/结果）；预算 max_global_steps=4 与 max_retries=2 相互独立
  - 服务层适配领域端口：MilvusService→VectorStore（不直连 SDK）、LLMService 结构化输出=JSON 容错+重试 1 次+安全默认、RerankerService=CrossEncoderScorer 懒加载+失败降级
  - **重大实测发现：langgraph 1.2.11 子图节点 custom 事件不上浮父图 astream**（探针证实）→ 事件机制改为 ContextVar 注入式发射器，适配器 astream=ainvoke+队列排空
  - **重大实测发现：本机 CPU（无 CUDA，8 线程）Qwen3-Reranker-0.6B 约 15s/对，一轮 20 对约 5 分钟**→ 粗排预截断 rerank_max_candidates=20 + RERANK_ENABLED 开关（默认 true 忠实设计；本机 .env 置 false 走 RRF 降级序，GPU 机器可开启）
  - grounding 双规则：检索路径要求【来源：…】/信息不足声明；直接回答路径只查编造法条；Web/Plugin 未开通跳过校验
  - SSE 契约向后兼容：新增 status 事件（node/label/phase/duration_ms，中文标签映射 constants.NODE_LABELS）；ChatService/SSE 路由补显式分支（status 不进 delta 聚合）
  - 旧实现机械搬迁 _legacy/ 规避同名冲突（graph/nodes/prompts/state 四文件），BE-038 切换装配时删除；BE-030 置 deprecated
- 运行过的验证：
  - 每功能全量 pytest 保持绿：154→168→189→195→216→185（删旧 31 例）→197；干净环境重置后终验 **197 passed**（unit 127 含 agent 76 / integration 70 含 agent 12 / api 9；真实 Milvus 5 例不可达时跳过）
  - 前端 npm run build 通过；浏览器实操（GLM+真实 Milvus+专利法）：法律问题生成中浅色状态行实时滚动（含"正在检索知识库…"与子图节点）+「检索策略（N 条查询）」面板→done 后 16 节点状态保留+「参考文档 10」；第二个法律问题一次成功引用第七十一条赔偿规则并标注来源；闲聊直接回答（无检索策略、无"暂无依据"声明、仅主图节点状态）；grounding 双打回→兜底谨慎回答路径真实触发一次
  - 真实 E2E（verify_real_e2e.py，GLM+Milvus，RERANK 关闭）：上传 TXT/MD 均 201 ready→plan 携带检索策略→15 节点 status 贯通→回答正确引用第四十二条"二十年"并标注【来源】→sources 与持久化一致→事件序 plan<sources<delta
  - 图可视化：export_qa_graph.py 桩依赖重导出 15 节点 Mermaid（docs/qa_graph.mmd，内嵌 ARCHITECTURE §5）
  - 验证后已清理：law_chunks 集合 drop、backend/data 删除、前后端进程停止
- 已记录证据：feature_list.json BE-032~041、FE-014/015、BE-040（passing）+ BE-030（deprecated）；对账 56=36 热层（32 passing+4 deprecated）+20 archived
- 已知风险或未解决问题：
  - Rerank 精排在 CPU 机器默认关闭（RERANK_ENABLED=false 降级 RRF 序）——功能已验证可跑通，GPU 机器开启即得精排
  - grounding LLM judge 存在模型行为方差（GLM 偶发首答缺【来源】被规则档打回；重生成+兜底路径已验证兜住）
  - 每问题 LLM 调用 5~8 次（忠实设计 D3），本地 Ollama 部署首字延迟明显（PLANNER_PROVIDER=glm 缓解规划环节）
  - Ollama LLM 路径的真实模型 E2E 未跑（本轮 E2E 走 GLM 配置；图闭环行为由集成测试锁定）
- 下一步最佳动作：可选产品增强（会话重命名/停止按钮/CORS 收敛）、MySQL 8.0 接入、或 Web Search 二期（替换 Stub 即可，suggested_external_queries 已透传备用）

