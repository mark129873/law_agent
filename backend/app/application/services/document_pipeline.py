"""文档处理 Pipeline：从原始文件到标准化 chunk 的编排层。

为什么放在 application 层：本类只做流程编排（识别→解析→清洗→切分），
不包含任何具体解析技术（那是解析器策略的事），
也不包含存储技术（入库是 EmbeddingService 与 VectorStore 的事）。
"""

from __future__ import annotations

import asyncio
import logging
import re

from app.domain.entities.chunk import DocumentChunk
from app.domain.services.document_parser import DocumentParser, UnsupportedFormatError

logger = logging.getLogger("app.document.pipeline")

# 控制字符（保留 \t\n 等常规空白）与连续空行的清洗规则
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTIPLE_BLANK_LINES = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """文本清洗：去控制字符、统一换行、压缩连续空行。

    为什么清洗独立成函数：切分质量直接决定检索质量，
    噪音字符进入 embedding 会稀释语义向量。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    text = _MULTIPLE_BLANK_LINES.sub("\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """段落感知切分：优先保持法条段落完整，单段超限时退化为滑动窗口。

    为什么不用纯定长窗口：法律文本一条法规就是一个语义单元，
    定长切分会把一条法条从中间截断（实测第四十二条的
    "期限为二十年"与后半句被切到两个 chunk，导致检索到也答不全）；
    按段落打包能让每条法条完整进入同一个 chunk。
    """
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    buffer = ""
    for paragraph in paragraphs:
        # 单段超过 chunk_size：无法保持完整，退化为定长滑动窗口（保留 overlap）
        if len(paragraph) > chunk_size:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            step = max(1, chunk_size - chunk_overlap)
            chunks.extend(paragraph[start : start + chunk_size] for start in range(0, len(paragraph), step))
            continue
        candidate = paragraph if not buffer else f"{buffer}\n{paragraph}"
        if len(candidate) <= chunk_size:
            buffer = candidate
        else:
            if buffer:
                chunks.append(buffer)
            buffer = paragraph
    if buffer:
        chunks.append(buffer)
    return chunks


class DocumentParserFactory:
    """按文件名选择解析器（工厂模式）。"""

    def __init__(self, parsers: list[DocumentParser]) -> None:
        self._parsers = parsers

    def get_parser(self, filename: str) -> DocumentParser:
        for parser in self._parsers:
            if parser.supports(filename):
                return parser
        raise UnsupportedFormatError(f"不支持的文档格式：{filename}（已注册解析器无法处理）")


class DocumentPipeline:
    """文档处理流水线：接收 → 识别 → 解析 → 清洗 → 切分 → chunk。"""

    def __init__(
        self,
        parser_factory: DocumentParserFactory,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> None:
        self._factory = parser_factory
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    @property
    def parser_factory(self) -> DocumentParserFactory:
        """公开只读访问：DocumentService 需要复用同一份格式识别规则。"""
        return self._factory

    async def process(self, filename: str, content: bytes) -> list[DocumentChunk]:
        """处理上传文件，返回可直接送入 Embedding/VectorStore 的 chunk 列表。"""
        logger.info(
            "Document processing started",
            extra={"service": "document_pipeline", "file_name": filename, "size": len(content)},
        )
        parser = self._factory.get_parser(filename)
        # 解析放到线程池：未来 PDF 解析是 CPU 密集操作，不能阻塞事件循环
        raw_text = await asyncio.to_thread(parser.parse, content)
        cleaned = clean_text(raw_text)
        pieces = chunk_text(cleaned, self._chunk_size, self._chunk_overlap)

        chunks = [
            DocumentChunk(
                # document_id 由调用方（上传服务）分配后回填，此处仅生成序号占位
                document_id="",
                content=piece,
                chunk_index=index,
                # 注意：chunk metadata 的键名是存储契约（Chroma/前端均依赖），
                # 与日志 extra 的保留字段限制无关，保持 "filename" 不变
                metadata={"filename": filename},
            )
            for index, piece in enumerate(pieces)
        ]
        logger.info(
            "Document processing completed",
            extra={
                "service": "document_pipeline",
                "file_name": filename,
                "chunk_count": len(chunks),
            },
        )
        return chunks
