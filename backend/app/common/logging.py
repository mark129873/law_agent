"""结构化 JSON 日志基础设施。

为什么这么做：docs/RELIABILITY.md 要求所有服务输出单行 JSON 日志，
便于事后问题分析与程序行为自动化监控；将格式化逻辑集中在此处，
后续任何服务只需通过 logging.getLogger 使用，避免各处手写格式。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

# 日志等级通过环境变量 LOG_LEVEL 控制，默认 ERROR（遵循 RELIABILITY.md 约定）
_DEFAULT_LEVEL = "ERROR"

# 保留字段集合：这些 key 属于日志条目顶层结构，业务数据统一放进 data，
# 防止业务字段意外覆盖框架字段导致日志解析歧义。
_RESERVED_KEYS = {"name", "msg", "args", "levelname", "levelno", "message", "data", "exc_info", "stack_info"}

# 已提升为日志顶层结构的 extra 字段：不应再重复出现在 data 中，
# 否则同一条信息会出现两份，增加日志体积且造成歧义。
_PROMOTED_EXTRA_KEYS = {"service"}

# LogRecord 的标准属性集合：这些是 logging 框架自带的内部字段，
# 不属于业务数据；若不过滤会把 pathname/thread 等噪音混进 data，
# 污染结构化日志的可读性与可解析性。
_RECORD_STD_ATTRS = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module", "msecs",
    "message", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "stack_print", "thread", "threadName",
    "taskName", "color_message",
}


class JsonFormatter(logging.Formatter):
    """把日志记录格式化为单行 JSON 对象。"""

    def format(self, record: logging.LogRecord) -> str:
        # 时间戳使用 UTC ISO8601 格式，保证跨机器排序与解析一致性
        timestamp = datetime.now(timezone.utc).isoformat()
        entry: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            # service 字段默认取 logger 名称，调用方可通过 extra={"service": ...} 覆盖
            "service": getattr(record, "service", record.name),
            "message": record.getMessage(),
        }
        # 合并调用方通过 extra 传入的业务字段到 data 中（排除框架内部属性）
        extra_data = {
            key: value
            for key, value in record.__dict__.items()
            if (
                key not in _RESERVED_KEYS
                and key not in _RECORD_STD_ATTRS
                and key not in _PROMOTED_EXTRA_KEYS
                and not key.startswith("_")
            )
        }
        if extra_data:
            entry["data"] = extra_data
        # 异常信息单独附加，避免丢失堆栈导致排障困难
        if record.exc_info:
            entry["data"] = entry.get("data", {}) | {"exception": self.formatException(record.exc_info)}
        return json.dumps(entry, ensure_ascii=False, default=str)


def setup_logging() -> None:
    """初始化根日志器：单行 JSON 输出到 stdout。

    为什么这么做：uvicorn 的控制台输出与业务日志混排时，
    统一走 stdout 且均为 JSON，才能保证日志可被工具链整行采集。
    """
    level_name = os.getenv("LOG_LEVEL", _DEFAULT_LEVEL).upper()
    level = getattr(logging, level_name, logging.ERROR)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    # 先清空默认 handler，避免重复输出普通文本日志
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn 自身的日志也统一为 JSON，保持输出格式一致
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
