"""Agent utils 纯函数单元测试（BE-032）。

覆盖去重优先级、查询汇总（顺序/去重/排除/截断）、证据转换与
trace 构造——全部无 IO，验证设计 §26/§33/§41/§48 的规则。
"""

from app.agent.subgraphs.legal_rag.state import EvidenceItem
from app.agent.utils import (
    Timer,
    chunk_to_evidence,
    collect_retrieval_queries,
    content_hash,
    dedup_candidates,
    evidence_to_source,
    format_evidence_context,
    make_trace,
    normalize_query_text,
)
from app.domain.entities.chunk import DocumentChunk, RetrievedChunk


def _item(**overrides) -> EvidenceItem:
    """构造测试证据条目（默认带 chunk_id 键）。"""
    base: EvidenceItem = {
        "id": "chunk-1",
        "document_id": "doc-1",
        "chunk_id": "chunk-1",
        "title": "专利法.txt",
        "content": "发明专利权的期限为二十年。",
        "query": "专利保护期限",
        "query_type": "original",
        "rrf_score": 0.03,
        "source_name": "专利法.txt",
        "metadata": {"filename": "专利法.txt", "chunk_index": 0},
    }
    base.update(overrides)
    return base


# ---- normalize_query_text / collect_retrieval_queries ----

def test_normalize_query_text_collapses_whitespace():
    assert normalize_query_text("  违法解除   劳动合同 \n赔偿 ") == "违法解除 劳动合同 赔偿"


def test_collect_queries_orders_and_types():
    queries = collect_retrieval_queries(
        "原始问题",
        rewritten_queries=["改写一", "改写二"],
        sub_queries=["子问题一"],
        expanded_queries=["扩展一", "扩展二", "扩展三"],
    )
    assert [q["query_type"] for q in queries] == [
        "original", "rewrite", "rewrite", "subquery", "expansion", "expansion", "expansion",
    ]
    assert queries[0]["query"] == "原始问题"


def test_collect_queries_dedups_and_excludes():
    queries = collect_retrieval_queries(
        "同一问题",
        rewritten_queries=["同一问题", "改写"],
        sub_queries=[" 同一问题 "],
        expanded_queries=[],
        exclude_texts={"改写"},
    )
    # 原文保留，重复与被排除文本不再出现
    assert [q["query"] for q in queries] == ["同一问题"]


def test_collect_queries_respects_include_original_and_cap():
    queries = collect_retrieval_queries(
        "原始",
        rewritten_queries=[f"改写{i}" for i in range(10)],
        sub_queries=[],
        expanded_queries=[],
        include_original=False,
        max_queries=3,
    )
    assert len(queries) == 3
    assert all(q["query_type"] == "rewrite" for q in queries)


# ---- content_hash / dedup_candidates ----

def test_content_hash_is_stable_and_short():
    assert content_hash("abc") == content_hash("abc")
    assert content_hash("abc") != content_hash("abd")
    assert len(content_hash("abc")) == 16


def test_dedup_prefers_chunk_id_over_doc_index():
    # 同 chunk_id 但 document_id 不同 → 仍按 chunk_id 合并（优先级最高）
    a = _item(chunk_id="c1", document_id="doc-A", rrf_score=0.01)
    b = _item(chunk_id="c1", document_id="doc-B", rrf_score=0.02)
    merged = dedup_candidates([a, b])
    assert len(merged) == 1
    assert merged[0]["rrf_score"] == 0.02  # 分数取最大


def test_dedup_merges_matched_queries():
    a = _item(query="问题一")
    b = _item(query="问题二")
    merged = dedup_candidates([a, b])
    assert len(merged) == 1
    assert merged[0]["matched_queries"] == ["问题一", "问题二"]


def test_dedup_falls_back_to_doc_index_then_content_hash():
    by_index_a = _item(chunk_id="", document_id="doc-1", metadata={"chunk_index": 3})
    by_index_b = _item(chunk_id="", document_id="doc-1", metadata={"chunk_index": 3})
    no_key = _item(chunk_id="", document_id="", metadata={}, content="相同内容")
    no_key_dup = _item(chunk_id="", document_id="", metadata={}, content="相同内容")
    merged = dedup_candidates([by_index_a, by_index_b, no_key, no_key_dup])
    assert len(merged) == 2  # doc+index 合并 2 条、content_hash 合并 2 条


def test_dedup_keeps_first_seen_order():
    a = _item(chunk_id="c2", content="B")
    b = _item(chunk_id="c1", content="A")
    merged = dedup_candidates([a, b])
    assert [m["chunk_id"] for m in merged] == ["c2", "c1"]


# ---- chunk_to_evidence / evidence_to_source / format_evidence_context ----

def test_chunk_to_evidence_maps_fields():
    chunk = DocumentChunk(
        document_id="doc-9",
        content="条文内容",
        chunk_index=2,
        metadata={"filename": "民法典.md"},
        chunk_id="chunk-9",
    )
    evidence = chunk_to_evidence(RetrievedChunk(chunk=chunk, score=0.05), "查询", "subquery")
    assert evidence["chunk_id"] == "chunk-9"
    assert evidence["query_type"] == "subquery"
    assert evidence["rrf_score"] == 0.05
    assert evidence["source_name"] == "民法典.md"


def test_evidence_to_source_uses_source_name():
    assert evidence_to_source(_item()) == {
        "source": "专利法.txt",
        "content": "发明专利权的期限为二十年。",
    }


def test_format_evidence_context_empty_returns_empty_string():
    assert format_evidence_context([]) == ""


def test_format_evidence_context_blocks():
    text = format_evidence_context([_item(), _item(source_name="另一部法.md", content="第二条")])
    assert text.startswith("【来源：专利法.txt】")
    assert "\n\n" in text
    assert "【来源：另一部法.md】" in text


# ---- make_trace / Timer ----

def test_make_trace_with_extra_counts():
    entry = make_trace("hybrid_retriever_node", "success", 123, extra={"query_count": 4})
    assert entry == {
        "node": "hybrid_retriever_node",
        "status": "success",
        "duration_ms": 123,
        "query_count": 4,
    }


def test_timer_measures_positive_elapsed():
    timer = Timer()
    assert timer.elapsed_ms() >= 0
