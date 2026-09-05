# 可靠性文档 — 可观测性、干净环境与基准测试

## 结构化日志
### 概述
应用内所有服务均输出结构化JSON日志条目，用于运行时调试、事后问题分析以及程序行为自动化监控。
### 日志格式
每一条日志为单行JSON对象：
```json
{
  "timestamp": "2026-03-30T12:00:00.000Z",
  "level": "INFO",
  "service": "xxx",
  "message": "xxx",
  "data": {
    "xxx": "xxx",
  }
}
```
### 日志级别
| 日志级别 | 使用场景 | 示例 |
|-------|-------------|---------|
| DEBUG | 常规数据访问、文件读取 | "Retrieved chunks for document" |
| INFO | 重要业务事件 | "Document imported", "Batch indexing complete" |
| WARN | 数据缺失但不影响主流程 | "Content not found for document" |
| ERROR | 程序运行失败 | "File not found during import" |

### 各服务日志埋点

**文档服务(DocumentService)：**
- 文档导入，记录文件大小与元数据
- 文档删除并输出剩余文档数量
- 文档元数据更新
- 文件未找到类错误
- 文件大小超限异常

**问答服务(QaService)：**
- 问答任务开始
- 生成回答，记录置信度与耗时
- 用户反馈提交
- 会话历史清空

### 日志等级配置
通过环境变量 `LOG_LEVEL` 设置日志输出等级：
LOG_LEVEL=INFO   # 输出 INFO、WARN、ERROR
LOG_LEVEL=ERROR # 仅输出 ERROR
默认值：`ERROR`

## 干净环境管理
### 作用
干净环境管理保证测试从一个已知的空白状态启动，避免历史遗留数据干扰测试结果，引发未知异常。

### 需要重置干净环境的场景
- 一轮调试结束之后
- 新功能测试之前
- 数据目录文件损坏时

### 干净环境校验
使用 `clean‑state‑checklist.md` 文件校验以下内容：
- 项目构建无报错
- 程序运行行为正常
- 日志输出符合预期
- 数据完整性校验通过
