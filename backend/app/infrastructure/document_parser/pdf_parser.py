"""PDF 文档解析器。

为什么逐页提取后拼接：法律 PDF 的条款常跨页断裂，
逐页提取保留页序，页间以换行分隔可避免相邻页句子粘连。
"""

from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.domain.services.document_parser import DocumentParser


class PdfParser(DocumentParser):
    """PDF 解析器，支持 .pdf 扩展名。"""

    def supports(self, filename: str) -> bool:
        return filename.lower().endswith(".pdf")

    def parse(self, content: bytes) -> str:
        try:
            reader = PdfReader(io.BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
        except (PdfReadError, ValueError, OSError) as error:
            # 损坏的 PDF 必须明确报错，让上层能标记文档为 failed
            raise ValueError(f"PDF 解析失败：文件损坏或格式非法（{error}）") from error

        text = "\n".join(page.strip() for page in pages if page.strip())
        if not text:
            # 扫描件/纯图片 PDF 无文本层，静默返回空串会导致下游产出空知识库
            raise ValueError("PDF 解析失败：未提取到任何文本（可能是扫描件或纯图片 PDF）")
        return text
