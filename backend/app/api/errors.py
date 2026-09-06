"""统一错误处理（BE-022）。

为什么集中处理：错误码与 HTTP 状态映射规则只能有一份，
散落在各路由会漂移；业务异常继承 AppError 即自动获得正确响应。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.dto import ErrorResponse

logger = logging.getLogger("app.api.errors")


class AppError(Exception):
    """业务异常基类：子类定义默认状态码与错误码。"""

    status_code = 400
    code = 40000

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConversationNotFoundApiError(AppError):
    status_code = 404
    code = 40401


class DocumentNotFoundApiError(AppError):
    status_code = 404
    code = 40402


class UnsupportedFormatApiError(AppError):
    status_code = 400
    code = 40001


class DocumentTooLargeApiError(AppError):
    status_code = 413
    code = 41301


def _error_response(status_code: int, code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=ErrorResponse(code=code, message=message).model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。"""

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "Business error",
            # 注意：不能使用 "message" 作为 extra 键——它是 LogRecord 保留字段，
            # 重名会使日志调用自身抛 KeyError，把 404 变成 500
            extra={"service": "api", "code": exc.code, "detail": exc.message},
        )
        return _error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 请求参数不合法：422 统一转译为业务错误形状，前端只需处理一种错误结构
        return _error_response(400, 40002, f"请求参数不合法：{exc.errors()[0].get('msg', 'invalid')}")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        # 兜底：任何未预期异常都返回 500 统一结构，同时记录 ERROR 日志
        logger.error(
            "Unexpected error",
            extra={"service": "api", "error": str(exc)},
            exc_info=exc,
        )
        return _error_response(500, 50000, "服务器内部错误")
