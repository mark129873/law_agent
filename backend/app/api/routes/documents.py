"""知识库文档路由（BE-021）。"""

from __future__ import annotations

from fastapi import APIRouter, Request, UploadFile

from app.api.dto import DocumentResponse
from app.api.errors import DocumentNotFoundApiError, DocumentTooLargeApiError, UnsupportedFormatApiError
from app.application.services.document_pipeline import UnsupportedFormatError
from app.application.services.document_service import DocumentNotFoundError, DocumentService, DocumentTooLargeError

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _get_document_service(request: Request) -> DocumentService:
    return request.app.state.container.resolve(DocumentService)


def _to_response(document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        file_size=document.file_size,
        status=document.status.value,
        created_at=document.created_at.isoformat(),
    )


@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(request: Request, file: UploadFile) -> DocumentResponse:
    """上传 PDF/TXT 并完成知识库入库。"""
    content = await file.read()
    try:
        document = await _get_document_service(request).upload_document(file.filename or "", content)
    except UnsupportedFormatError as error:
        raise UnsupportedFormatApiError(str(error)) from error
    except DocumentTooLargeError as error:
        raise DocumentTooLargeApiError(str(error)) from error
    return _to_response(document)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(request: Request) -> list[DocumentResponse]:
    return [_to_response(d) for d in await _get_document_service(request).list_documents()]


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: str, request: Request) -> None:
    try:
        await _get_document_service(request).delete_document(document_id)
    except DocumentNotFoundError as error:
        raise DocumentNotFoundApiError(str(error)) from error
