"""少量 HTTP/SSE 冒烟：验证真实产品链路，不承担完整质量评测。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from app.evaluation.models import EvaluationCase


async def prepare_corpus(
    base_url: str,
    *,
    reset_eval: bool,
    data_dir: str | Path | None = None,
) -> dict[str, Any]:
    """通过公开文档 API 清理并重新导入当前仓库测试数据源中的文档。

    不直接 drop Milvus collection：运行中的服务可能缓存集合状态，
    通过文档删除接口可以同时清理 SQLite 元数据和向量内容。
    """
    _require_eval_collection()
    root = Path(data_dir) if data_dir else Path(__file__).resolve().parents[2] / "tests" / "data_source"
    files = sorted(path for path in root.iterdir() if path.is_file() and path.suffix.lower() in {".md", ".txt", ".pdf"})
    if not files:
        raise ValueError(f"测试数据源为空：{root}")

    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=300.0) as client:
        if reset_eval:
            response = await client.get("/api/documents")
            _raise_http(response, "读取文档列表")
            for document in response.json():
                deleted = await client.delete(f"/api/documents/{document['id']}")
                _raise_http(deleted, f"删除文档 {document['id']}")

        uploaded: list[dict[str, Any]] = []
        for path in files:
            response = await client.post(
                "/api/documents",
                files={"file": (path.name, path.read_bytes(), _content_type(path))},
            )
            _raise_http(response, f"上传文档 {path.name}")
            uploaded.append(response.json())

    return {"base_url": base_url, "reset_eval": reset_eval, "uploaded": uploaded}


async def run_api_smoke(base_url: str, cases: list[EvaluationCase]) -> dict[str, Any]:
    """执行一个有依据问题和一个无依据问题，校验 SSE 与持久化契约。"""
    _require_eval_collection()
    success = next((case for case in cases if case.expected_status == "SUCCESS" and case.expected_sources), None)
    insufficient = next((case for case in cases if case.expected_status == "LOCAL_EVIDENCE_INSUFFICIENT"), None)
    if success is None or insufficient is None:
        raise ValueError("数据集必须同时包含 SUCCESS 有依据案例和 LOCAL_EVIDENCE_INSUFFICIENT 案例")

    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=300.0) as client:
        success_result = await _smoke_question(client, success, require_sources=True)
        insufficient_result = await _smoke_question(client, insufficient, require_sources=False)

    result = {
        "base_url": base_url,
        "passed": bool(success_result["passed"] and insufficient_result["passed"]),
        "cases": [success_result, insufficient_result],
    }
    return result


async def _smoke_question(
    client: httpx.AsyncClient,
    case: EvaluationCase,
    *,
    require_sources: bool,
) -> dict[str, Any]:
    conversation = await client.post("/api/conversations", json={"title": f"evaluation-{case.id}"})
    _raise_http(conversation, "创建评测会话")
    conversation_id = conversation.json()["id"]
    response = await client.post(
        "/api/chat/stream",
        json={"conversation_id": conversation_id, "question": case.question, "use_web_search": case.use_web_search},
    )
    _raise_http(response, f"SSE 问答 {case.id}")
    events = _parse_sse(response.text)
    types = [str(event.get("type")) for event in events]
    sources = [event for event in events if event.get("type") == "sources"]
    source_payload = sources[-1].get("sources", []) if sources else []
    messages = await client.get(f"/api/conversations/{conversation_id}/messages")
    _raise_http(messages, "读取评测消息")
    message_items = messages.json()
    assistant_sources = message_items[-1].get("sources") if message_items else None
    has_plan = "plan" in types

    checks = {
        "status_seen": "status" in types,
        # 有本地证据的 RAG 路径必须展示检索计划；证据不足/直接回答路径
        # 可以跳过 plan，但仍需保证 delta 与 done 的顺序完整。
        "status_before_plan": _before(types, "status", "plan") if has_plan else not require_sources,
        "plan_before_delta": _before(types, "plan", "delta") if has_plan else not require_sources,
        "delta_seen": "delta" in types,
        "done_last": bool(types) and types[-1] == "done",
        "sources_when_expected": bool(sources) if require_sources else not sources,
        "sources_persisted": assistant_sources == source_payload if require_sources else True,
        "no_raw_secret_or_stack": _safe_response(response.text, events),
    }
    if require_sources:
        checks["sources_before_delta"] = _before(types, "sources", "delta")
    passed = all(checks.values())
    return {
        "case_id": case.id,
        "question": case.question,
        "passed": passed,
        "event_types": types,
        "checks": checks,
        "conversation_id": conversation_id,
    }


def _parse_sse(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload:
            events.append(json.loads(payload))
    return events


def _before(types: list[str], first: str, second: str) -> bool:
    try:
        return types.index(first) < types.index(second)
    except ValueError:
        return False


def _safe_response(text: str, events: list[dict[str, Any]]) -> bool:
    haystack = text + json.dumps(events, ensure_ascii=False)
    forbidden = ["Traceback", "GLM_API_KEY", "TAVILY_API_KEY", "Authorization"]
    forbidden.extend(value for value in os.environ.values() if value and len(value) >= 8)
    return not any(marker in haystack for marker in forbidden)


def _require_eval_collection() -> None:
    """阻止 prepare/api-smoke 误连正式知识库。"""
    collection = os.environ.get("MILVUS_COLLECTION_NAME", "")
    if not collection.startswith("law_agent_eval"):
        raise RuntimeError(
            "评测入口要求 MILVUS_COLLECTION_NAME 以 law_agent_eval 开头，"
            "请先配置独立 Milvus 集合。"
        )


def _content_type(path: Path) -> str:
    return {".md": "text/markdown", ".txt": "text/plain", ".pdf": "application/pdf"}.get(
        path.suffix.lower(), "application/octet-stream"
    )


def _raise_http(response: httpx.Response, action: str) -> None:
    if response.is_error:
        # HTTP 错误正文可能来自第三方组件，冒烟工具只保留状态码，避免把
        # 堆栈、请求头或远端配置意外打印到终端和报告。
        raise RuntimeError(f"{action}失败：HTTP {response.status_code}")
