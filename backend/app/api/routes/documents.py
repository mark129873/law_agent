"""知识库文档路由。

DDD 说明：上传接口把 multipart 解码为 (filename, bytes) 后交给
DocumentService，路由不感知解析/入库流程；领域与应用层异常在此
统一翻译为 4xx 错误码，保证异常翻译只发生在 API 边界一处。
"""

from __future__ import annotations

from fastapi import APIRouter, Request, UploadFile

from app.api.dto import DocumentResponse
from app.api.errors import DocumentNotFoundApiError, DocumentTooLargeApiError, UnsupportedFormatApiError
from app.application.services.document_pipeline import UnsupportedFormatError
from app.application.services.document_service import DocumentNotFoundError, DocumentService, DocumentTooLargeError

# 路由前缀统一挂在 /api/documents 下，具体端点只写子路径
router = APIRouter(prefix="/api/documents", tags=["documents"])


def _get_document_service(request: Request) -> DocumentService:
    """从容器解析文档服务：依赖装配集中在容器，路由保持轻薄。"""
    return request.app.state.container.resolve(DocumentService)


def _to_response(document) -> DocumentResponse:
    """领域实体 → 响应 DTO：枚举转字符串、时间转 ISO，实体不出 API 层。"""
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        file_size=document.file_size,
        status=document.status.value,
        created_at=document.created_at.isoformat(),
    )


@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(request: Request, file: UploadFile) -> DocumentResponse:
    """上传 PDF/TXT/MD 文档并完成知识库入库（解析→向量化→写入 Chroma）。

    响应中的 status 已是终态（ready/failed），前端据此直接展示
    成功或失败，无需轮询处理进度。
    """
    # UploadFile 是流式文件对象：这里一次性读入内存——大小上限
    # （20MB）由服务层校验兜底，保证超限文件不会撑爆内存
    content = await file.read()
    try:
        # file.filename 可能为 None：服务层按空文件名走格式识别，必然拒绝
        document = await _get_document_service(request).upload_document(file.filename or "", content)
    except UnsupportedFormatError as error:
        # 领域/应用层异常 → API 错误码：翻译只发生在 API 边界一处
        raise UnsupportedFormatApiError(str(error)) from error
    except DocumentTooLargeError as error:
        raise DocumentTooLargeApiError(str(error)) from error
    return _to_response(document)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(request: Request) -> list[DocumentResponse]:
    """文档列表（创建时间倒序），供前端知识库管理页渲染。"""
    return [_to_response(d) for d in await _get_document_service(request).list_documents()]


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: str, request: Request) -> None:
    """删除文档：服务层级联清理向量内容与元数据，两侧必须同时清空。"""
    try:
        await _get_document_service(request).delete_document(document_id)
    except DocumentNotFoundError as error:
        # 领域异常 → API 错误：翻译只在这里发生，Service 层不感知 HTTP
        raise DocumentNotFoundApiError(str(error)) from error
