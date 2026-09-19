"""评测数据准备：复用文档 API 导入测试语料，避免重复实现入库逻辑。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx


async def prepare_corpus(
    base_url: str,
    *,
    reset: bool,
    data_dir: str | Path | None = None,
) -> dict[str, Any]:
    """通过公开文档 API 可选清理后，导入当前仓库测试数据源中的文档。

    不直接 drop Milvus collection：运行中的服务可能缓存集合状态，
    通过文档删除接口可以同时清理 SQLite 元数据和向量内容。
    """
    root = Path(data_dir) if data_dir else Path(__file__).resolve().parents[2] / "tests" / "data_source"
    files = sorted(path for path in root.iterdir() if path.is_file() and path.suffix.lower() in {".md", ".txt", ".pdf"})
    if not files:
        raise ValueError(f"测试数据源为空：{root}")

    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=300.0) as client:
        if reset:
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

    return {"base_url": base_url, "reset": reset, "uploaded": uploaded}


def _content_type(path: Path) -> str:
    return {".md": "text/markdown", ".txt": "text/plain", ".pdf": "application/pdf"}.get(
        path.suffix.lower(), "application/octet-stream"
    )


def _raise_http(response: httpx.Response, action: str) -> None:
    if response.is_error:
        # HTTP 错误正文可能来自第三方组件，导入工具只保留状态码，避免把
        # 堆栈、请求头或远端配置意外打印到终端和报告。
        raise RuntimeError(f"{action}失败：HTTP {response.status_code}")
