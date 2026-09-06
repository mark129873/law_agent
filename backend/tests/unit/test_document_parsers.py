"""PDF 与 TXT 解析器测试。

为什么在测试里生成真实 PDF：BE-012 的验收标准是"PDF 和 TXT 测试文件
均能够正确提取文本"，手工伪造的字节流无法代表真实 PDF 结构；
用 fpdf2 在测试内生成合法 PDF 文件，保证用例自包含且可信。
"""

import io

import pytest
from fpdf import FPDF

from app.application.services.document_pipeline import DocumentParserFactory, DocumentPipeline
from app.infrastructure.document_parser.pdf_parser import PdfParser
from app.infrastructure.document_parser.text_parser import TextParser


def _make_pdf(text: str) -> bytes:
    """生成包含指定文本的单页 PDF（标准 Helvetica 字体，拉丁文本）。"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    pdf.cell(0, 10, text=text)
    return bytes(pdf.output())


def test_factory_routes_by_extension() -> None:
    """工厂应按扩展名分发：pdf 走 PdfParser，txt 走 TextParser。"""
    factory = DocumentParserFactory([TextParser(), PdfParser()])
    assert isinstance(factory.get_parser("劳动合同.pdf"), PdfParser)
    assert isinstance(factory.get_parser("劳动法.txt"), TextParser)
    assert isinstance(factory.get_parser("笔记.MD"), TextParser)


@pytest.mark.asyncio
async def test_pdf_parsed_through_pipeline() -> None:
    """真实 PDF 文件经 Pipeline 提取文本并产出 chunk。"""
    pdf_bytes = _make_pdf("This contract clause governs breach damages and remedies.")
    pipeline = DocumentPipeline(
        parser_factory=DocumentParserFactory([TextParser(), PdfParser()]),
        chunk_size=100,
        chunk_overlap=10,
    )
    chunks = await pipeline.process("contract.pdf", pdf_bytes)
    assert len(chunks) >= 1
    joined = "".join(c.content for c in chunks)
    assert "breach damages" in joined
    assert all(c.metadata["filename"] == "contract.pdf" for c in chunks)


@pytest.mark.asyncio
async def test_corrupted_pdf_fails_loudly() -> None:
    """损坏的 PDF 必须抛出明确异常，不能静默产出空 chunk。"""
    pipeline = DocumentPipeline(parser_factory=DocumentParserFactory([PdfParser()]))
    with pytest.raises(ValueError, match="PDF 解析失败"):
        await pipeline.process("broken.pdf", b"this is not a pdf at all")


@pytest.mark.asyncio
async def test_text_pdf_without_text_layer_fails() -> None:
    """无文本层的合法 PDF（如空白页）也应明确报错而不是返回空结果。"""
    pdf = FPDF()
    pdf.add_page()
    empty_pdf_bytes = bytes(pdf.output())
    pipeline = DocumentPipeline(parser_factory=DocumentParserFactory([PdfParser()]))
    with pytest.raises(ValueError, match="未提取到任何文本"):
        await pipeline.process("scanned.pdf", empty_pdf_bytes)


def test_text_parser_encoding_fallback() -> None:
    """GBK 编码的 TXT 应能正确解码（utf-8 失败后回退 gb18030）。"""
    gbk_bytes = "劳动合同违约金条款".encode("gb18030")
    assert TextParser().parse(gbk_bytes) == "劳动合同违约金条款"


def test_text_parser_rejects_binary_garbage() -> None:
    """任何编码都解不开的二进制内容应明确报错。"""
    with pytest.raises(ValueError, match="文本解码失败"):
        TextParser().parse(bytes(range(0x80, 0x100)) * 4)
