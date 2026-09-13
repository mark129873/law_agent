"""Agent 节点解析函数单元测试（BE-030）。

parse_sub_queries / parse_judge_verdict 是纯函数（无 IO），
覆盖规划器与判分器小模型输出的各种失控形态。
"""

from app.agent._legacy.nodes import parse_judge_verdict, parse_sub_queries

# ---- parse_sub_queries ----


def test_parse_sub_queries_valid_array() -> None:
    assert parse_sub_queries('["劳动合同违约金", "经济补偿标准"]', "原问题") == [
        "劳动合同违约金",
        "经济补偿标准",
    ]


def test_parse_sub_queries_json_in_code_block() -> None:
    """模型把 JSON 包进 markdown 代码块时仍可解析。"""
    raw = '```json\n["子查询A"]\n```'
    assert parse_sub_queries(raw, "原问题") == ["子查询A"]


def test_parse_sub_queries_unparsable_falls_back() -> None:
    """输出不是 JSON：回退为透传原问题（规划是增强而非闸门）。"""
    assert parse_sub_queries("我觉得应该检索一下相关法条", "原问题") == ["原问题"]


def test_parse_sub_queries_empty_array_falls_back() -> None:
    assert parse_sub_queries("[]", "原问题") == ["原问题"]


def test_parse_sub_queries_non_string_items_falls_back() -> None:
    """数组元素不是字符串（如嵌套对象）：整体回退。"""
    assert parse_sub_queries('[{"q": "x"}]', "原问题") == ["原问题"]


def test_parse_sub_queries_over_limit_truncated() -> None:
    """子查询数超上限时截断，保护检索成本。"""
    raw = '["a", "b", "c", "d", "e"]'
    assert parse_sub_queries(raw, "原问题") == ["a", "b", "c"]


def test_parse_sub_queries_strips_whitespace_and_drops_empty() -> None:
    assert parse_sub_queries('["  a  ", "", "b"]', "原问题") == ["a", "b"]


# ---- parse_judge_verdict ----


def test_parse_judge_verdict_pass() -> None:
    report = parse_judge_verdict('{"verdict": "pass", "feedback": "", "unsupported": []}')
    assert report is not None
    assert report["verdict"] == "pass"


def test_parse_judge_verdict_grounding_with_unsupported() -> None:
    raw = '{"verdict": "grounding", "feedback": "需补充检索", "unsupported": ["结论A", "结论B"]}'
    report = parse_judge_verdict(raw)
    assert report is not None
    assert report["verdict"] == "grounding"
    assert report["unsupported"] == ["结论A", "结论B"]


def test_parse_judge_verdict_invalid_verdict_is_none() -> None:
    """verdict 不在三态清单内：视为不可解析（调用方按 pass 放行）。"""
    assert parse_judge_verdict('{"verdict": "excellent"}') is None


def test_parse_judge_verdict_unparsable_is_none() -> None:
    assert parse_judge_verdict("回答看起来不错！") is None
    assert parse_judge_verdict("") is None


def test_parse_judge_verdict_missing_fields_defaults() -> None:
    """缺省字段给安全默认值，不抛异常。"""
    report = parse_judge_verdict('{"verdict": "contract"}')
    assert report is not None
    assert report["feedback"] == ""
    assert report["unsupported"] == []
