"""文档处理 Pipeline 测试。

为什么覆盖清洗与切分细节：chunk 质量直接决定 RAG 检索质量；
BE-011 的验收标准是"输入支持的文档后能够经过统一 Pipeline
转换为标准化 document chunks"，必须验证 chunk 的完整性与元数据。
"""

import pytest

from app.application.services.document_pipeline import (
    DocumentParserFactory,
    DocumentPipeline,
    chunk_text,
    clean_text,
)
from app.domain.services.document_parser import UnsupportedFormatError
from app.infrastructure.document_parser.text_parser import TextParser


@pytest.fixture
def pipeline() -> DocumentPipeline:
    """小切分参数的 Pipeline：便于用少量文本验证多 chunk 行为。"""
    return DocumentPipeline(
        parser_factory=DocumentParserFactory([TextParser()]),
        chunk_size=20,
        chunk_overlap=5,
    )


@pytest.mark.asyncio
async def test_txt_flows_through_pipeline(pipeline: DocumentPipeline) -> None:
    """TXT 文件经 Pipeline 产出带序号与来源元数据的标准化 chunk。"""
    content = "劳动合同违约金条款。劳动报酬支付规定。民法典合同编总则。" * 5
    chunks = await pipeline.process("劳动法问答.txt", content.encode("utf-8"))

    assert len(chunks) > 1  # 内容超过 chunk_size，必须切分
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(len(c.content) <= 20 for c in chunks)
    assert all(c.metadata["filename"] == "劳动法问答.txt" for c in chunks)
    assert all(c.document_id == "" for c in chunks)  # id 由上传服务分配


@pytest.mark.asyncio
async def test_unsupported_format_rejected(pipeline: DocumentPipeline) -> None:
    """未注册解析器的格式应在识别阶段立即失败。"""
    with pytest.raises(UnsupportedFormatError):
        await pipeline.process("恶意脚本.exe", b"MZ...")


@pytest.mark.asyncio
async def test_cleaning_removes_control_chars(pipeline: DocumentPipeline) -> None:
    """控制字符与 \r\n 应在清洗阶段被处理，不进入 chunk。"""
    raw = "第一段\x00内容。\r\n第二段\x07内容。"
    chunks = await pipeline.process("清洗测试.txt", raw.encode("utf-8"))
    joined = "".join(c.content for c in chunks)
    assert "\x00" not in joined
    assert "\x07" not in joined
    assert "\r" not in joined


def test_chunk_text_overlap_keeps_boundary_context() -> None:
    """相邻 chunk 应存在重叠，保证边界语义连续。"""
    text = "abcdefghij" * 3  # 30 字符
    pieces = chunk_text(text, chunk_size=10, chunk_overlap=4)
    assert len(pieces) >= 4
    # step = 10-4 = 6，第二个 chunk 的开头应与第一个 chunk 的尾部重叠
    assert pieces[1][0] == text[6]


def test_clean_text_normalizes_blank_lines() -> None:
    """连续空行应被压缩，首尾空白应被去除。"""
    cleaned = clean_text("  第一段\n\n\n\n\n第二段  \n")
    assert cleaned == "第一段\n\n第二段"
