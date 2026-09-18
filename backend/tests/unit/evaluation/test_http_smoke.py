"""BE-049 SSE 解析器和安全边界测试。"""

from app.evaluation.http_smoke import _before, _parse_sse, _safe_response


def test_parse_sse_reads_json_data_frames() -> None:
    events = _parse_sse(
        'data: {"type":"plan"}\n\n'
        'data: {"type":"done"}\n\n'
    )

    assert [event["type"] for event in events] == ["plan", "done"]
    assert _before(["status", "plan", "delta", "done"], "plan", "delta") is True
    assert "plan" not in [event["type"] for event in _parse_sse('data: {"type":"delta"}\n\ndata: {"type":"done"}\n\n')]


def test_safe_response_rejects_stack_and_secret_markers() -> None:
    assert _safe_response('{"type":"done"}', []) is True
    assert _safe_response("Traceback (most recent call last)", []) is False
    assert _safe_response('{"message":"GLM_API_KEY=secret"}', []) is False
