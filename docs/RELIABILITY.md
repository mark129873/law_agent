# 可靠性文档 — 可观测性、干净环境与基准测试

## 结构化日志规则

### 概述
应用内所有服务均输出结构化 JSON 日志条目，用于运行时调试、事后问题分析以及程序行为自动化监控。日志同时写入 **stdout** 与 **本地文件**：stdout 供开发期实时查看与容器采集，文件供服务端事后追溯（stdout 会随进程/容器销毁而丢失）。

### 日志基础设施
- 实现位置：`backend/app/common/logging.py`（`JsonFormatter` + `setup_logging()`，在应用启动时初始化）。
- **双 sink、同一格式**：stdout 与 `backend/log/app.log` 必须复用同一个 `JsonFormatter`，避免两处格式各自演进产生漂移。
- 日志等级与目录等配置统一经 `config/settings.py` 读取（`LOG_LEVEL` / `LOG_DIR` / `LOG_FILE_NAME` / `LOG_BACKUP_COUNT`），**禁止在日志模块内散读环境变量**；`.env` 中的配置同样生效。
- 每条日志为**单行 JSON 对象**，示例：

```json
{
  "timestamp": "2026-03-30T12:00:00.123Z",
  "level": "INFO",
  "service": "chat",
  "request_id": "8f3c1a2b",
  "message": "Chat stream completed",
  "data": { "conversation_id": "...", "answer_length": 130 }
}
```

### 日志字段契约
- `timestamp`：UTC 时间，ISO-8601 **毫秒精度、以 `Z` 结尾**（如 `2026-03-30T12:00:00.123Z`）。统一该格式是为了跨机器、跨语言解析与排序一致；禁止使用本地时间、禁止省略 `Z`。
- `level`：`DEBUG` / `INFO` / `WARN` / `ERROR`（Python 的 `WARNING` 统一归一为 `WARN`）。
- `service`：产生日志的模块，取值必须来自下方受控清单；默认取 logger 名称，业务调用一律通过 `extra={"service": ...}` 显式指定，避免出现 `app.main` 之类的裸 logger 名。
- `message`：人类可读的简短描述（英文短语），不得包含敏感数据。
- `data`：业务字段统一放入此处（`logger.info(msg, extra={...})`），字段名用 snake_case。
- `request_id`：单次请求的链路标识（HTTP 中间件生成并经 `contextvars` 注入），用于把「HTTP 请求 → 检索 → LLM 调用 → 落库」串成一条线；无请求上下文的后台任务可省略。
- `exception`：`ERROR` 级别必须带异常类型与堆栈（`logger.exception` / `exc_info=True`），禁止只写一句话的 ERROR。
- **字段只增不改**：新增字段属兼容变更；重命名或删除字段必须同步更新本文档与该字段的下游消费方（监控、日志分析脚本）。

`service` 受控清单：

| service | 归属 |
|---------|------|
| `system` | 应用生命周期、健康检查、全局异常兜底 |
| `agent` | Agent 图节点执行（一期重写：意图路由/编排/检索规划/查询变体/混合检索/重排/证据评估/恢复/回答/校验/确定性收尾）；每节点起止各一条 INFO（"Agent node started/completed"，data.node + data.duration_ms），节点状态同时以 status SSE 事件外推（前端浅色过程展示，BE-041）；LLM 节点 data 含 model 与业务计数；精排主动关闭记 INFO，模型加载/推理失败才记 WARN（"Agent reranker failed, degraded to RRF order"） |
| `api` | API 层业务异常与未预期异常处理 |
| `database` | 数据库连接与建表 |
| `vector_store` | 向量库（Milvus）初始化与读写 |
| `document` | 文档元数据状态机、上传与删除 |
| `document_pipeline` | 解析 → 清洗 → 段落切分 Pipeline |
| `knowledge` | 向量化与入库编排 |
| `embedding` | 向量生成服务 |
| `rag` | 检索与上下文构建 |
| `web_search` | Tavily Remote MCP 搜索调用、搜索结果落盘与失败状态 |
| `conversation` | 会话生命周期与消息持久化 |
| `chat` | 问答编排与流式输出 |
| `llm` | 模型调用 |
| `uvicorn.error` / `uvicorn.access` | uvicorn 自带日志（已归一为同格式） |

### 日志落盘与轮转
- **目录**：`backend/log/`（相对路径锚定 `backend/`，不随进程工作目录变化；可用 `LOG_DIR` 覆盖）。该目录**不入库**（见 `.gitignore`）。
- **文件**：`app.log`，按天轮转（`TimedRotatingFileHandler`，`when=midnight`，UTC），归档名为 `app.log.YYYY-MM-DD`，**默认保留 30 天**（可用 `LOG_BACKUP_COUNT` 覆盖）。
- **编码**：文件 handler 必须显式 `encoding="utf-8"`，否则 Windows 下中文日志可能乱码。
- **多进程**：当前部署为单进程（uvicorn 未开 `--workers`），按天轮转安全；若将来启用多 worker，多进程会竞争同一文件，必须改为按 PID 分文件或集中式采集，不得直接沿用当前配置。

### 联网搜索独立留档
- 每次用户实际触发的 Tavily 搜索都生成一个独立文件：`LOG_DIR/web_search/search-<UTC时间>-<UUID>.log`；文件内容是完整 JSON，而不是仅写摘要。
- 留档字段至少包括 `search_id`、`timestamp`、`request_id`、`conversation_id`、`query`、`tool_name`、脱敏后的参数、`status`、`duration_ms`、完整 MCP `content`/`structured_content`、完整规范化结果和错误信息。
- 搜索日志永久保留，不参与 `app.log` 的按天轮转，也不由测试干净环境自动删除；需要清理时由运维人工执行。`backend/log/` 仍必须保持 gitignore。
- 写入采用“临时文件 + 原子替换”，文件名使用 UTC 时间和 UUID，避免并发搜索互相覆盖。API Key 与 Authorization 只放在 MCP 请求头，禁止写入搜索日志、结构化日志、SSE 或前端。
- 搜索结果未成功落盘时，搜索能力返回失败状态并向用户发出提示，不把未留档的数据继续作为成功答案展示；该失败必须同时记录 ERROR（含堆栈）。

### 使用约定（重要，曾踩坑）
- `extra` 的键**禁止使用 LogRecord 保留字段**（`message`、`filename`、`name` 等）——重名会使日志调用自身抛 `KeyError`，曾导致业务 404 变成 500（由 API 集成测试在 `LOG_LEVEL=INFO` 下抓出）。
- **密钥禁止进日志**：`GLM_API_KEY`、`TAVILY_API_KEY`、`MILVUS_CLOUD_TOKEN` 等敏感值不得出现在任何日志字段中；日志只允许记录模型名、工具名、消息数、长度、Milvus 是否使用认证等非敏感元数据。
- **脱敏兜底**：`JsonFormatter` 对 `api_key`、`token`、`password`、`authorization`、`secret` 等敏感键名做黑名单处理（值替换为 `***`），作为"密钥禁止进日志"约定的机械保障，防止误写。

### 日志级别
| 日志级别 | 使用场景 | 示例 |
|-------|-------------|---------|
| DEBUG | 常规数据访问、文件读取 | "Retrieved chunks for document" |
| INFO | 重要业务事件 | "Chat stream completed", "Document upload completed" |
| WARN | 数据缺失但不影响主流程 | "Document produced no chunks" |
| ERROR | 程序运行失败 | "Document ingestion failed", "Unexpected error" |

### 日志等级配置
通过环境变量 `LOG_LEVEL`（或 `backend/.env` 中的同名配置）设置日志输出等级：
```text
LOG_LEVEL=INFO   # 输出 INFO、WARN、ERROR（默认值）
LOG_LEVEL=DEBUG  # 排障时临时开启，输出常规数据访问轨迹
LOG_LEVEL=ERROR  # 仅输出 ERROR
```
- 默认 `INFO`：保证"重要业务事件"（如 `Chat stream completed`）默认可见；需要完整数据访问轨迹时才显式开启 `DEBUG`。
- 取值优先级：进程环境变量 > `backend/.env` > 默认值。

### 各服务日志埋点规则
按上方级别表在必要位置埋点：重要业务事件记 INFO、数据缺失但不影响主流程记 WARN、程序运行失败记 ERROR（必须带堆栈）。示例——DocumentService：上传记录文件大小与元数据、大小超限异常、删除输出剩余数量、元数据更新、文件未找到类错误；QaService：问答任务开始、检索结果（命中数与最高相似度）、回答生成（首 token 延迟/总耗时/长度——推理模型首字延迟是已知痛点必须可度量）、流式异常中断（区分模型侧与网络侧）、会话历史清空；WebSearch：搜索开始/完成/失败分别记录 `search_id`、结果数、耗时和留档路径，失败必须带堆栈。

## Langfuse 链路追踪（BE-043）

- **开关与配置**：`LANGFUSE_ENABLED`（默认 false）+ `LANGFUSE_BASE_URL` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`（密钥只经 .env/环境注入，禁止提交与落日志）。关闭时 langfuse 模块零导入、零开销；开启但密钥缺失 → 启动期 WARN 降级为关闭（可观测故障不阻断业务）。
- **采集范围**：每问一条 trace（session_id=conversation_id，input=问题，output=完整回答）→ 节点 span（with_node_status 包装器统一压栈/弹栈，含子图嵌套与异常路径）→ LLM generation（LLMService 统一入口：model/messages/output/耗时/重试轮次）；plan/think/sources/regenerating 记为 trace 事件留档。
- **失败降级**：LangfuseTraceSink 全部方法内部吞异常并记 WARN（`service=trace`）——Langfuse 不可达或上报失败绝不影响问答业务。
- **与日志的分工**：结构化日志是"进程内排障事实"（必开、落盘）；Langfuse 是"跨请求 LLM 观测平台"（默认关、可选开）。两者共用同一计时源与节点名，不互相替代。

## RAG 端到端评测（BE-049）

- **执行范围**：评测使用真实 LLM、Embedding、Milvus 和 Reranker；工作流直调负责质量指标，HTTP/SSE 只负责产品路径冒烟。
- **数据隔离**：评测必须使用独立的 `MILVUS_COLLECTION_NAME`，默认不得清理 `law_chunks`；评测 SQLite 数据也应使用单独路径。
- **报告内容**：报告记录数据集版本、Git commit、Provider、模型名、指标、耗时和失败原因；敏感配置只记录“已配置/未配置”或模型名，禁止写入 API Key、Authorization 和完整环境变量。
- **真实模型波动**：LLM Judge 结果不是确定性 CI 门禁。评测脚本遇到单条超时或 Judge 失败时继续执行并记录该案例，只有基础设施不可用、数据格式非法或报告无法写入时才返回非零退出码。
- **Judge 约束**：Judge 只能依据问题、评测要点、系统回答、检索证据和引用评分，不允许把外部知识当作证据；Judge 模型与回答模型的实际名称必须写入报告。
- **原始报告**：`backend/log/evaluation/` 属于排障和演示文档工件，保持 gitignore，不随普通测试清理删除；提交前只保留脱敏的汇总报告。

## 测试干净环境管理 

### 作用
干净环境管理保证测试从一个已知的空白状态启动，避免历史遗留数据干扰测试结果，引发未知异常。

### 重置机制 (测试前需运行)
1. 删除 sqlite数据库中的原先的测试数据
2. 删除 Milvus 中的知识库集合：默认云端配置下必须显式执行 `cd backend && uv run python scripts/reset_milvus.py --yes`；本地 standalone 可执行不带参数的脚本。脚本幂等删除 `law_chunks` 集合，下次启动/入库自动重建。
   **警告：云端集合可能是正式数据，只有确认目标 Endpoint 和集合后才允许执行 `--yes`。**
3. 删除完成之后, 明确输出: 测试干净环境管理完成, 清理xxx文件, 删除xxx数据库内容

### 需要重置干净环境的场景
- 开工测试之前
- 收尾测试之前时
- 数据目录文件损坏时（数据位置见 ARCHITECTURE.md 第 6 节：`backend/data/`，已被 gitignore）

### 日志目录不参与重置
`backend/log/` 保存的是排障证据，**不随测试干净环境重置删除**；其体积由按天轮转与保留策略（默认 30 天）治理，需要彻底清理时人工删除该目录即可。
