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
| `api` | API 层业务异常与未预期异常处理 |
| `database` | 数据库连接与建表 |
| `vector_store` | 向量库初始化与读写 |
| `document` | 文档元数据状态机、上传与删除 |
| `document_pipeline` | 解析 → 清洗 → 段落切分 Pipeline |
| `knowledge` | 向量化与入库编排 |
| `embedding` | 向量生成服务 |
| `rag` | 检索与上下文构建 |
| `conversation` | 会话生命周期与消息持久化 |
| `chat` | 问答编排与流式输出 |
| `llm` | 模型调用 |
| `uvicorn.error` / `uvicorn.access` | uvicorn 自带日志（已归一为同格式） |

### 日志落盘与轮转
- **目录**：`backend/log/`（相对路径锚定 `backend/`，不随进程工作目录变化；可用 `LOG_DIR` 覆盖）。该目录**不入库**（见 `.gitignore`）。
- **文件**：`app.log`，按天轮转（`TimedRotatingFileHandler`，`when=midnight`，UTC），归档名为 `app.log.YYYY-MM-DD`，**默认保留 30 天**（可用 `LOG_BACKUP_COUNT` 覆盖）。
- **编码**：文件 handler 必须显式 `encoding="utf-8"`，否则 Windows 下中文日志可能乱码。
- **多进程**：当前部署为单进程（uvicorn 未开 `--workers`），按天轮转安全；若将来启用多 worker，多进程会竞争同一文件，必须改为按 PID 分文件或集中式采集，不得直接沿用当前配置。

### 使用约定（重要，曾踩坑）
- `extra` 的键**禁止使用 LogRecord 保留字段**（`message`、`filename`、`name` 等）——重名会使日志调用自身抛 `KeyError`，曾导致业务 404 变成 500（由 API 集成测试在 `LOG_LEVEL=INFO` 下抓出）。
- **密钥禁止进日志**：`GLM_API_KEY` 等敏感值不得出现在任何日志字段中；日志只允许记录模型名、消息数、长度等非敏感元数据。
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
根据实际需要, 在必要位置埋点, 记录重要业务事件、数据缺失但不影响主流程、程序运行失败等。示例:
**文档服务(DocumentService)：**
- 文档导入，记录文件大小与元数据
- 文档删除并输出剩余文档数量
- 文档元数据更新
- 文件未找到类错误
- 文件大小超限异常
**问答服务(QaService)：**
- 问答任务开始
- 检索结果（命中数量与最高相似度）
- 生成回答，记录首 token 延迟、总耗时与回答长度（推理模型首字延迟是本项目已知痛点，必须可度量）
- 流式回答异常中断（记录失败原因，便于区分模型侧与网络侧）
- 会话历史清空
**等等**



## 测试干净环境管理

### 作用
干净环境管理保证测试从一个已知的空白状态启动，避免历史遗留数据干扰测试结果，引发未知异常。

### 重置机制
1. 删除本地数据库与向量库文件 `backend/data/`, 里面存放的均为测试遗留数据, 可以直接删除

### 需要重置干净环境的场景
- 开工测试之前
- 收尾测试之前时
- 数据目录文件损坏时（数据位置见 ARCHITECTURE.md 第 6 节：`backend/data/`，已被 gitignore）

### 日志目录不参与重置
`backend/log/` 保存的是排障证据，**不随测试干净环境重置删除**；其体积由按天轮转与保留策略（默认 30 天）治理，需要彻底清理时人工删除该目录即可。
