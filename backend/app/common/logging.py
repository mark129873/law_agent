"""结构化 JSON 日志基础设施。

为什么这么做：docs/RELIABILITY.md 要求所有服务输出单行 JSON 日志，
并**同时落盘到 backend/log/** 供服务端事后追溯（stdout 会随进程/容器销毁而丢失）。
把「格式化 + 双 sink 装配 + 请求链路标识 + 敏感字段脱敏」集中在此处，
任何服务只需 logging.getLogger 即可获得一致行为，避免各处重复实现导致格式漂移。

设计模式：
- 单例/单点装配：setup_logging() 是进程内唯一的日志装配入口；
- 过滤器（Filter）：把 request_id 这一横切关注点统一附加到每条记录，
  业务代码零感知（对应 AOP 思想）；
- 模板方法：JsonFormatter 固定日志条目骨架，业务只填 data。
DDD/OOP：本模块属 common 横切基础设施，不承载业务规则，仅依赖 config 层的配置对象。
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from app.config.settings import Settings, get_settings

# 日志等级默认 INFO（遵循 RELIABILITY.md）：保证"重要业务事件"默认可见
_DEFAULT_LEVEL = "INFO"

# 请求链路标识：由 HTTP 中间件写入，日志过滤器读取后附加到每条记录。
# 为什么用 ContextVar 而不是线程局部变量：异步应用里多个请求在事件循环中
# 交错执行，ContextVar 才能保证 request_id 不串到别的请求上。
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# 敏感键名黑名单：命中即把值替换为 ***（机械兜底，防止密钥误写进日志）。
# 这是"密钥禁止进日志"约定的最后一道防线，而非唯一防线。
_SENSITIVE_KEYWORDS = ("api_key", "apikey", "token", "password", "authorization", "secret")
_MASK = "***"

# 保留字段集合：这些 key 属于日志条目顶层结构，业务数据统一放进 data，
# 防止业务字段意外覆盖框架字段导致日志解析歧义。
_RESERVED_KEYS = {"name", "msg", "args", "levelname", "levelno", "message", "data", "exc_info", "stack_info"}

# 已提升为日志顶层结构的 extra 字段：不应再重复出现在 data 中，
# 否则同一条信息会出现两份，增加日志体积且造成歧义。
_PROMOTED_EXTRA_KEYS = {"service", "request_id"}

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


def set_request_id(request_id: str) -> Token[str]:
    """设置当前请求的链路标识，返回可用于还原的 Token。

    为什么返回 Token：请求结束时必须还原上下文，否则在复用任务（如后台任务）
    中会残留上一个请求的标识，造成日志张冠李戴。
    """
    return _request_id_var.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    """还原请求链路标识（请求处理结束时调用）。"""
    _request_id_var.reset(token)


def get_request_id() -> str:
    """读取当前请求链路标识；无请求上下文时返回空串。"""
    return _request_id_var.get()


class RequestContextFilter(logging.Filter):
    """把当前请求的 request_id 注入每条日志记录。

    为什么用 Filter：request_id 是横切关注点，由过滤器统一附加才能保证
    业务代码零修改、零遗漏；缺失上下文（启动期、脚本）时不附加该字段。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        current = get_request_id()
        if current:
            record.request_id = current
        return True


def _mask_sensitive(value: Any) -> Any:
    """递归脱敏：字典中命中敏感键名的值替换为 ***，列表逐项递归。"""
    if isinstance(value, dict):
        return {
            key: (
                _MASK
                if any(word in str(key).lower() for word in _SENSITIVE_KEYWORDS)
                else _mask_sensitive(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_mask_sensitive(item) for item in value]
    return value


def _utc_millis() -> str:
    """返回 UTC ISO-8601 毫秒精度时间戳（如 2026-03-30T12:00:00.123Z）。

    为什么固定成毫秒 + Z：跨机器、跨语言的解析与排序要一致；
    本地时间与可变精度（微秒/无 Z）会让日志工具链产生歧义。
    """
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class JsonFormatter(logging.Formatter):
    """把日志记录格式化为单行 JSON 对象。"""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": _utc_millis(),
            # WARNING 归一为 WARN，与 RELIABILITY.md 声明的等级取值保持一致
            "level": "WARN" if record.levelname == "WARNING" else record.levelname,
            # service 默认取 logger 名称，调用方可通过 extra={"service": ...} 覆盖
            "service": getattr(record, "service", record.name),
            "message": record.getMessage(),
        }
        # 请求链路标识：仅在存在请求上下文时输出，避免无意义空字段
        request_id = getattr(record, "request_id", "")
        if request_id:
            entry["request_id"] = request_id
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
            # 统一脱敏：作为"密钥禁止进日志"的机械兜底
            entry["data"] = _mask_sensitive(extra_data)
        # 异常信息单独附加，避免丢失堆栈导致排障困难
        if record.exc_info:
            entry["data"] = entry.get("data", {}) | {"exception": self.formatException(record.exc_info)}
        return json.dumps(entry, ensure_ascii=False, default=str)


def _build_handlers(settings: Settings, formatter: JsonFormatter) -> list[logging.Handler]:
    """构造双 sink：stdout + backend/log 按天轮转文件。

    为什么文件 handler 容错：日志基础设施故障（磁盘满/权限不足/路径非法）
    绝不能把业务请求变成 5xx；此处失败即降级为仅 stdout，绝不向上抛出。
    """
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        log_dir = Path(settings.resolved_log_dir)
        # 目录自愈：不存在则幂等创建（与 backend/data/ 首次启动自愈同一思路）
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            TimedRotatingFileHandler(
                filename=str(log_dir / settings.log_file_name),
                when="midnight",
                utc=True,
                backupCount=settings.log_backup_count,
                # 显式 utf-8：否则 Windows 下中文日志可能乱码
                encoding="utf-8",
                # delay=True：首次真正写入时才开文件，避免空跑时也占用句柄
                delay=True,
            )
        )
    except OSError:
        # 静默降级：无文件 sink 也要保证 stdout 可用
        pass
    for handler in handlers:
        handler.setFormatter(formatter)
        # 过滤器挂在 handler 上：经根日志器输出的记录都会带上 request_id
        handler.addFilter(RequestContextFilter())
    return handlers


def setup_logging(settings: Settings | None = None) -> None:
    """初始化根日志器：stdout + backend/log 双 sink，单行 JSON。

    为什么幂等：应用启动、测试夹具、脚本都可能调用本函数；重复调用时
    必须先关闭并移除旧 handler——Windows 下不关闭会占用日志文件句柄，
    导致轮转/删除失败。配置统一经 Settings 读取，不在本模块散读环境变量。
    """
    config = settings or get_settings()
    level = getattr(logging, config.log_level.upper(), logging.getLevelName(_DEFAULT_LEVEL))

    handlers = _build_handlers(config, JsonFormatter())

    root = logging.getLogger()
    # 先关闭并清空默认/历史 handler，避免重复输出与句柄泄漏
    for old_handler in list(root.handlers):
        root.removeHandler(old_handler)
        old_handler.close()
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)

    # uvicorn 自身的日志也统一为 JSON，保持输出格式一致
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
