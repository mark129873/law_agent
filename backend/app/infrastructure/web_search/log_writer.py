"""联网搜索独立日志文件写入器。

每次搜索使用一个唯一文件，而不是给标准 logging 动态增加 handler：
动态 handler 在并发请求和 Windows 文件句柄管理下容易互相影响。
这里采用 Writer/Repository 风格的小型基础设施对象，负责目录自愈、
JSON 序列化和原子替换；业务状态仍由 Tavily 适配器负责。
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SENSITIVE_KEYWORDS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
)
_MASK = "***"


def _mask_sensitive(value: Any) -> Any:
    """对日志对象做递归兜底脱敏，避免未来新增字段误写密钥。"""
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
    if isinstance(value, tuple):
        return [_mask_sensitive(item) for item in value]
    return value


def _file_timestamp() -> str:
    """生成适合 Windows 文件名的 UTC 时间戳。"""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


class WebSearchLogWriter:
    """把一次搜索的完整记录原子写入独立 `.log` 文件。"""

    def __init__(self, log_dir: str | Path) -> None:
        # 目录由 Settings 锚定到 backend/，Writer 不散读环境变量。
        self._directory = Path(log_dir) / "web_search"

    @property
    def directory(self) -> Path:
        """返回搜索日志目录，供状态检查和测试使用。"""
        return self._directory

    def write(self, record: dict[str, Any]) -> Path:
        """写入一条完整 JSON 记录并返回最终路径。

        为什么先写临时文件再 os.replace：进程中断或并发写入时，用户不会
        看到半个 JSON 文件；os.replace 在同一文件系统内是原子的。
        """
        self._directory.mkdir(parents=True, exist_ok=True)
        target = self._directory / f"search-{_file_timestamp()}-{uuid.uuid4().hex}.log"
        temp_path: Path | None = None
        try:
            # NamedTemporaryFile 在 Windows 下关闭后才允许 os.replace，
            # 因此这里显式 delete=False 并在 finally 中清理临时文件。
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=self._directory,
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(_mask_sensitive(record), handle, ensure_ascii=False, indent=2, default=str)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, target)
            temp_path = None
            return target
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
