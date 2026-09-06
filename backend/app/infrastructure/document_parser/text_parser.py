"""文本（TXT/Markdown）解析器。

为什么用多编码回退：本地法律文本常见 UTF-8 与 GBK 两种编码，
仅支持 UTF-8 会把大量既有文档判为"解析失败"，故按序尝试常见编码。
"""

from __future__ import annotations

from app.domain.services.document_parser import DocumentParser

# 依次尝试的文本编码：utf-8 优先（失败代价为零的快速路径），国标编码兜底
_SUPPORTED_ENCODINGS = ("utf-8", "gb18030", "big5")


class TextParser(DocumentParser):
    """纯文本解析器，支持 .txt 与常见文本扩展名。"""

    def supports(self, filename: str) -> bool:
        lower = filename.lower()
        return lower.endswith((".txt", ".md", ".text"))

    def parse(self, content: bytes) -> str:
        last_error: UnicodeDecodeError | None = None
        for encoding in _SUPPORTED_ENCODINGS:
            try:
                return content.decode(encoding)
            except UnicodeDecodeError as error:
                last_error = error
        # 全部编码失败：明确报错，交由上层记录 ERROR 日志并返回失败状态
        raise ValueError(f"文本解码失败：已尝试编码 {_SUPPORTED_ENCODINGS}") from last_error
