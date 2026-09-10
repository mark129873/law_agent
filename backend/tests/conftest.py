"""pytest 全局配置。

为什么需要：日志现在会落盘（docs/RELIABILITY.md）。若测试沿用默认的
`backend/log/`，每次跑测试都会往工作区写日志文件，并可能与开发日志混杂。
这里在导入任何应用代码之前把 `LOG_DIR` 指向系统临时目录，保证 pytest
进程产生的日志不污染仓库；开发/生产行为不受影响（仅在本进程内生效）。

使用 `setdefault`：若本地已显式设置 `LOG_DIR`（想临时观察测试日志），则尊重该值。
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault("LOG_DIR", tempfile.mkdtemp(prefix="law_agent_test_log_"))
