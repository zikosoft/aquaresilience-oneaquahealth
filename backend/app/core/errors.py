"""Consistent JSON error envelope for the whole API.

Envelope shape:
{
  "error": {
    "code": "string machine code",
    "message": "human readable message",
    "details": {...} | null
  }
}
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Base application error mapped to a stable error code + HTTP status."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found", details: dict | None = None) -> None:
        super().__init__("NOT_FOUND", message, status.HTTP_404_NOT_FOUND, details)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Authentication required", details: dict | None = None) -> None:
        super().__init__("UNAUTHORIZED", message, status.HTTP_401_UNAUTHORIZED, details)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Insufficient permissions", details: dict | None = None) -> None:
        super().__init__("FORBIDDEN", message, status.HTTP_403_FORBIDDEN, details)


class ConflictError(AppError):
    def __init__(self, message: str = "Resource conflict", details: dict | None = None) -> None:
        super().__init__("CONFLICT", message, status.HTTP_409_CONFLICT, details)


class RateLimitedError(AppError):
    def __init__(self, message: str = "Too many requests", details: dict | None = None) -> None:
        super().__init__("RATE_LIMITED", message, status.HTTP_429_TOO_MANY_REQUESTS, details)


def _envelope(code: str, message: str, details: Any = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_envelope(exc.code, exc.message, exc.details))

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "HTTP_ERROR"
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            code = "NOT_FOUND"
        elif exc.status_code == status.HTTP_401_UNAUTHORIZED:
            code = "UNAUTHORIZED"
        elif exc.status_code == status.HTTP_403_FORBIDDEN:
            code = "FORBIDDEN"
        detail = exc.detail if isinstance(exc.detail, str) else "An error occurred"
        return JSONResponse(status_code=exc.status_code, content=_envelope(code, detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope("VALIDATION_ERROR", "Request validation failed", exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Never leak stack traces / internals to the client.
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("INTERNAL_ERROR", "An unexpected error occurred"),
        )
