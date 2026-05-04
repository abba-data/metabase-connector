from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException


class ErrorCode:
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    METABASE_TIMEOUT = "METABASE_TIMEOUT"
    METABASE_UNAVAILABLE = "METABASE_UNAVAILABLE"
    EXCEEDED_SYNC_WINDOW = "EXCEEDED_SYNC_WINDOW"
    METABASE_ERROR = "METABASE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    request_id: str
    debug: dict[str, Any] | None = Field(default=None)


class ConnectorError(Exception):
    status_code: int = 500
    code: str = ErrorCode.INTERNAL_ERROR

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        debug: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.debug = debug


class UnauthorizedError(ConnectorError):
    status_code = 401
    code = ErrorCode.UNAUTHORIZED


class ForbiddenError(ConnectorError):
    status_code = 403
    code = ErrorCode.FORBIDDEN


class RateLimitedError(ConnectorError):
    status_code = 429
    code = ErrorCode.RATE_LIMITED


class MetabaseTimeoutError(ConnectorError):
    status_code = 504
    code = ErrorCode.METABASE_TIMEOUT


class MetabaseUnavailableError(ConnectorError):
    status_code = 503
    code = ErrorCode.METABASE_UNAVAILABLE


class ExceededSyncWindowError(ConnectorError):
    status_code = 504
    code = ErrorCode.EXCEEDED_SYNC_WINDOW


class MetabaseError(ConnectorError):
    status_code = 502
    code = ErrorCode.METABASE_ERROR


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _envelope_response(
    *,
    code: str,
    message: str,
    request_id: str,
    status_code: int,
    debug: dict[str, Any] | None = None,
) -> JSONResponse:
    body = ErrorEnvelope(
        code=code, message=message, request_id=request_id, debug=debug
    ).model_dump(exclude_none=True)
    return JSONResponse(status_code=status_code, content=body)


async def connector_error_handler(request: Request, exc: ConnectorError) -> JSONResponse:
    return _envelope_response(
        code=exc.code,
        message=exc.message,
        request_id=_request_id(request),
        status_code=exc.status_code,
        debug=exc.debug,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return _envelope_response(
        code=ErrorCode.VALIDATION_ERROR,
        message="Request failed validation.",
        request_id=_request_id(request),
        status_code=422,
        debug={"errors": jsonable_encoder(exc.errors())},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = {
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        429: ErrorCode.RATE_LIMITED,
    }.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    return _envelope_response(
        code=code,
        message=str(exc.detail),
        request_id=_request_id(request),
        status_code=exc.status_code,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return _envelope_response(
        code=ErrorCode.INTERNAL_ERROR,
        message="Unhandled error.",
        request_id=_request_id(request),
        status_code=500,
        debug={"type": type(exc).__name__},
    )
