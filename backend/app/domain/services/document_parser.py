"""文档解析器策略接口。

为什么用策略模式：支持的文档格式会持续增加（txt/pdf/...），
把"如何从文件字节提取文本"封装为独立策略，
Pipeline 与格式细节完全解耦，新增格式零侵入。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class UnsupportedFormatError(Exception):
    """文件格式不被任何已注册解析器支持。"""


class DocumentParser(ABC):
    """文档解析器契约：文件字节 → 纯文本。"""

    @abstractmethod
    def supports(self, filename: str) -> bool:
        """判断本解析器是否支持该文件名（按扩展名）。"""

    @abstractmethod
    def parse(self, content: bytes) -> str:
        """解析文件字节并返回纯文本；解析失败应抛出异常而不是返回空串。"""
