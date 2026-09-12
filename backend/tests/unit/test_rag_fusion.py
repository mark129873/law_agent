"""RRF（Reciprocal Rank Fusion）融合函数单元测试（BE-028）。

融合是纯函数逻辑，与任何存储无关，单独验证：
多路去重叠加、单路保序、top_k 截断与 score 契约。
"""

from app.application.services.rag_service import reciprocal_rank_fusion
from app.domain.entities.chunk import DocumentChunk, RetrievedChunk


def _result(chunk_id: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=DocumentChunk(chunk_id=chunk_id, document_id="doc", content=f"内容{chunk_id}"),
        score=0.9,  # 原始分数应被 RRF 得分覆盖
    )


def test_fusion_merges_channels_and_boosts_overlapping_chunks() -> None:
    """两路同时命中的 chunk 得分叠加应排第一（"两路都认为相关"）。"""
    vector_channel = [_result("a"), _result("b")]  # a 第 1、b 第 2
    keyword_channel = [_result("b"), _result("c")]  # b 第 1、c 第 2
    fused = reciprocal_rank_fusion([vector_channel, keyword_channel], top_k=3)
    # b 在两路分别贡献 1/(60+2)+1/(60+1)，稳居第一
    assert [r.chunk.chunk_id for r in fused] == ["b", "a", "c"]


def test_fusion_deduplicates_same_chunk_across_channels() -> None:
    """同一 chunk 在两路出现时只输出一条（按 chunk_id 去重）。"""
    fused = reciprocal_rank_fusion([[_result("a"), _result("a")], [_result("a")]], top_k=5)
    assert [r.chunk.chunk_id for r in fused] == ["a"]


def test_fusion_single_channel_preserves_ranking() -> None:
    """单路输入（纯向量回退路径）应保持原排名不变。"""
    fused = reciprocal_rank_fusion([[_result("x"), _result("y"), _result("z")]], top_k=3)
    assert [r.chunk.chunk_id for r in fused] == ["x", "y", "z"]


def test_fusion_respects_top_k() -> None:
    """输出数量不超过 top_k。"""
    channel = [_result(i) for i in "abcde"]
    fused = reciprocal_rank_fusion([channel], top_k=2)
    assert len(fused) == 2


def test_fusion_scores_descending_and_positive() -> None:
    """RRF 得分应严格降序且为正（保持 RetrievedChunk 越大越相关契约）。"""
    fused = reciprocal_rank_fusion([[_result("a"), _result("b")], [_result("c")]], top_k=3)
    scores = [r.score for r in fused]
    assert all(score > 0 for score in scores)
    assert scores == sorted(scores, reverse=True)


def test_fusion_empty_channels_returns_empty() -> None:
    """两路均无命中时应返回空列表（衔接"信息不足"策略）。"""
    assert reciprocal_rank_fusion([[], []], top_k=4) == []
