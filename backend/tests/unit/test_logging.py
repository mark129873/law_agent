"""结构化日志契约测试（docs/RELIABILITY.md）。

为什么单独立契约测试：日志格式是对外可解析契约，而"落盘、脱敏、失败降级、
幂等、请求链路标识"这些行为一旦回归，很难在业务测试里被发现，必须机械守护。
所有用例都把日志目录指向 tmp_path，避免污染 backend/log/。
"""

from __future__ import annotations

import json
import logging
import re
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.common.logging import (
    JsonFormatter,
    RequestContextFilter,
    reset_request_id,
    set_request_id,
    setup_logging,
)
from app.config.settings import Settings

# UTC ISO-8601 毫秒精度 + Z 结尾（RELIABILITY.md 字段契约）
_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    """构造测试配置：日志目录锚定 tmp_path，避免污染仓库。"""
    return Settings(
        log_dir=str(tmp_path / "log"),
        log_file_name="app.log",
        log_level="INFO",
        _env_file=None,
        **overrides,  # type: ignore[arg-type]
    )


def _make_record(logger: logging.Logger, msg: str, extra: dict[str, object]) -> logging.LogRecord:
    """构造带 extra 业务字段的日志记录，供格式化器契约断言使用。"""
    return logger.makeRecord(
        name=logger.name,
        level=logging.INFO,
        fn=__file__,
        lno=1,
        msg=msg,
        args=(),
        exc_info=None,
        extra=extra,
    )


def test_formatter_outputs_single_line_json_with_required_fields() -> None:
    """单行 JSON + 必需字段齐全，且时间戳符合 UTC 毫秒 + Z 规范。"""
    record = _make_record(logging.getLogger("test.logging"), "Chat stream completed", {"service": "chat", "answer_length": 130})
    line = JsonFormatter().format(record)

    assert "\n" not in line
    entry = json.loads(line)
    assert entry["level"] == "INFO"
    assert entry["service"] == "chat"
    assert entry["message"] == "Chat stream completed"
    assert entry["data"]["answer_length"] == 130
    assert _TIMESTAMP_PATTERN.match(entry["timestamp"]), entry["timestamp"]


def test_formatter_normalizes_warning_level_to_warn() -> None:
    """logging 的 WARNING 必须归一为契约中的 WARN。"""
    record = logging.getLogger("test.logging").makeRecord(
        name="test.logging", level=logging.WARNING, fn=__file__, lno=1,
        msg="low hit", args=(), exc_info=None, extra={"service": "rag"},
    )
    assert json.loads(JsonFormatter().format(record))["level"] == "WARN"


def test_service_is_promoted_and_not_duplicated_in_data() -> None:
    """service 提升到顶层后，不应再重复出现在 data 中（避免歧义与体积膨胀）。"""
    record = _make_record(logging.getLogger("test.logging"), "svc", {"service": "chat", "conversation_id": "c1"})
    entry = json.loads(JsonFormatter().format(record))
    assert entry["service"] == "chat"
    assert "service" not in entry["data"]
    assert entry["data"]["conversation_id"] == "c1"


def test_sensitive_keys_are_masked() -> None:
    """敏感键名（api_key/token 等）必须被替换为 ***，作为"密钥禁止进日志"的兜底。"""
    record = _make_record(
        logging.getLogger("test.logging"),
        "model call",
        {"service": "llm", "api_key": "sk-secret", "model": "glm", "nested": {"access_token": "t-1"}},
    )
    data = json.loads(JsonFormatter().format(record))["data"]
    assert data["api_key"] == "***"
    assert data["model"] == "glm"
    assert data["nested"]["access_token"] == "***"


def test_request_id_injected_from_context() -> None:
    """请求上下文存在时，request_id 出现在日志顶层；结束后不再出现。"""
    logger = logging.getLogger("test.logging")
    token = set_request_id("req-abc")
    try:
        record = _make_record(logger, "in request", {"service": "chat"})
        RequestContextFilter().filter(record)  # 等价于 handler 上挂载的过滤器
        assert json.loads(JsonFormatter().format(record))["request_id"] == "req-abc"
    finally:
        reset_request_id(token)

    outside = _make_record(logger, "outside request", {"service": "chat"})
    RequestContextFilter().filter(outside)
    assert "request_id" not in json.loads(JsonFormatter().format(outside))


def test_logging_writes_utf8_json_line_to_file(tmp_path: Path) -> None:
    """落盘契约：backend/log 下生成文件，内容为单行 JSON 且中文正常。"""
    settings = _settings(tmp_path)
    setup_logging(settings)

    logging.getLogger("test.file").info("落盘中文检查", extra={"service": "system"})
    for handler in logging.getLogger().handlers:
        handler.flush()

    log_file = Path(settings.resolved_log_dir) / settings.log_file_name
    assert log_file.exists()
    entry = json.loads(log_file.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert entry["message"] == "落盘中文检查"
    assert entry["service"] == "system"


def test_file_handler_uses_daily_rotation_and_retention(tmp_path: Path) -> None:
    """轮转参数契约：按天（midnight, UTC）轮转 + 保留天数可配 + utf-8。"""
    setup_logging(_settings(tmp_path, log_backup_count=7))

    file_handlers = [h for h in logging.getLogger().handlers if isinstance(h, TimedRotatingFileHandler)]
    assert len(file_handlers) == 1
    handler = file_handlers[0]
    assert handler.when == "MIDNIGHT"
    assert handler.backupCount == 7
    assert (handler.encoding or "").lower() == "utf-8"


def test_unwritable_log_dir_degrades_to_stdout_only(tmp_path: Path) -> None:
    """写盘不可用（路径被文件占用）时必须降级为仅 stdout，且绝不抛异常。"""
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x", encoding="utf-8")

    setup_logging(Settings(log_dir=str(blocker), log_level="INFO", _env_file=None))  # type: ignore[call-arg]

    handlers = logging.getLogger().handlers
    assert all(not isinstance(h, TimedRotatingFileHandler) for h in handlers)
    # 降级后 stdout 仍然可用
    logging.getLogger("test.degrade").warning("still works", extra={"service": "system"})


def test_setup_logging_is_idempotent(tmp_path: Path) -> None:
    """重复调用不得叠加 handler（否则日志重复输出、句柄泄漏）。"""
    settings = _settings(tmp_path)
    setup_logging(settings)
    first = len(logging.getLogger().handlers)
    setup_logging(settings)
    assert len(logging.getLogger().handlers) == first == 2  # stdout + 文件
