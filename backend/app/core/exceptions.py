"""Application error types and the global exception handlers.

Every error leaves the API in one shape::

    {
      "error": {
        "code": "SOME_ERROR_CODE",
        "message": "Human-readable message",
        "request_id": "uuid",
        "details": {}
      }
    }
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.core.request_context import REQUEST_ID_HEADER, get_request_id

logger = get_logger(__name__)

# Starlette renamed its 422 constant between versions; pin the numeric code.
HTTP_422_UNPROCESSABLE = 422


class AppError(Exception):
    """Base class for errors this application raises deliberately."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details: dict[str, Any] = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"
    message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    message = "The request conflicts with the current state of the resource."


class ValidationError(AppError):
    status_code = HTTP_422_UNPROCESSABLE
    code = "VALIDATION_ERROR"
    message = "The request payload failed validation."


class ImmutableRecordError(AppError):
    """Raised when code attempts to mutate an append-only record."""

    status_code = status.HTTP_409_CONFLICT
    code = "IMMUTABLE_RECORD"
    message = "This record is append-only and cannot be modified or deleted."


class DatabaseUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "DATABASE_UNAVAILABLE"
    message = "The database is not reachable."


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build the canonical error envelope."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
                "details": details or {},
            }
        },
        headers={REQUEST_ID_HEADER: request_id},
    )


_HTTP_STATUS_CODES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    status.HTTP_409_CONFLICT: "CONFLICT",
    HTTP_422_UNPROCESSABLE: "VALIDATION_ERROR",
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
}


def register_exception_handlers(app: FastAPI) -> None:
    """Install the handlers that guarantee the error envelope."""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = get_request_id()
        logger.warning(
            "application_error",
            error_code=exc.code,
            status_code=exc.status_code,
            path=request.url.path,
            detail=exc.message,
        )
        return error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            request_id=request_id,
            details=exc.details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = get_request_id()
        code = _HTTP_STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
        return error_response(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
            request_id=request_id,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = get_request_id()
        return error_response(
            status_code=HTTP_422_UNPROCESSABLE,
            code="VALIDATION_ERROR",
            message="The request payload failed validation.",
            request_id=request_id,
            details={"errors": _jsonable_errors(exc.errors())},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        request_id = get_request_id()
        logger.exception(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            exc_type=type(exc).__name__,
        )
        return error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_ERROR",
            message="An unexpected error occurred.",
            request_id=request_id,
        )


def _jsonable_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip non-serialisable bits (e.g. exception instances) from pydantic errors."""
    cleaned: list[dict[str, Any]] = []
    for error in errors:
        cleaned.append({k: v for k, v in error.items() if k != "ctx"} | _ctx(error))
    return cleaned


def _ctx(error: dict[str, Any]) -> dict[str, Any]:
    ctx = error.get("ctx")
    if not isinstance(ctx, dict):
        return {}
    return {"ctx": {k: str(v) for k, v in ctx.items()}}
