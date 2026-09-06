# 可靠性文档 — 可观测性、干净环境与基准测试

## 结构化日志

### 概述
应用内所有服务均输出结构化 JSON 日志条目，用于运行时调试、事后问题分析以及程序行为自动化监控。

### 日志基础设施
- 实现位置：`backend/app/common/logging.py`（`JsonFormatter` + `setup_logging()`，在应用导入时初始化）。
- 每条日志为**单行 JSON 对象**，输出到 stdout, 示例：

```json
{
  "timestamp": "2026-03-30T12:00:00.000Z",
  "level": "INFO",
  "service": "chat",
  "message": "Chat stream completed",
  "data": { "conversation_id": "...", "answer_length": 130 }
}
```

- `service` 标识产生日志的模块；业务字段统一放入 `data`（通过 `logger.info(msg, extra={...})` 传入）。
- uvicorn 自身的启动/访问日志已归一为同格式（`service: uvicorn.error / uvicorn.access`）。
- 使用约定（重要，曾踩坑）：
  - `extra` 的键**禁止使用 LogRecord 保留字段**（`message`、`filename`、`name` 等）——重名会使日志调用自身抛 `KeyError`，曾导致业务 404 变成 500（由 API 集成测试在 LOG_LEVEL=INFO 下抓出）。
  - **密钥禁止进日志**：`GLM_API_KEY` 等敏感值不得出现在任何日志字段中；日志只允许记录模型名、消息数、长度等非敏感元数据。

### 日志级别
| 日志级别 | 使用场景 | 示例 |
|-------|-------------|---------|
| DEBUG | 常规数据访问、文件读取 | "Retrieved chunks for document" |
| INFO | 重要业务事件 | "Chat stream completed", "Document upload completed" |
| WARN | 数据缺失但不影响主流程 | "Document produced no chunks" |
| ERROR | 程序运行失败 | "Document ingestion failed", "Unexpected error" |

### 日志等级配置
通过环境变量 `LOG_LEVEL` 设置日志输出等级：
```text
LOG_LEVEL=INFO   # 输出 INFO、WARN、ERROR
LOG_LEVEL=ERROR  # 仅输出 ERROR（默认值）
```
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
- 生成回答，记录置信度与耗时
- 会话历史清空
**等等**


## 干净环境管理

### 作用
干净环境管理保证测试从一个已知的空白状态启动，避免历史遗留数据干扰测试结果，引发未知异常。

### 需要重置干净环境的场景
- 一轮调试结束之后
- 新功能测试之前
- 数据目录文件损坏时（数据位置见 ARCHITECTURE.md 第 6 节：`backend/data/`，已被 gitignore）

### 干净环境校验
使用仓库根目录的 `clean-state-checklist.md` 文件校验以下内容：
- 项目构建无报错
- 程序运行行为正常
- 日志输出符合预期
- 数据完整性校验通过
