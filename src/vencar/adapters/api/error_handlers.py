import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from vencar.domain.errors import ErrorCode, VencarError

logger = logging.getLogger(__name__)

STATUS_BY_CODE = {
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.ASSESSMENT_NOT_FOUND: 404,
    ErrorCode.ASSESSMENT_BUSY: 409,
    ErrorCode.TOO_MANY_PHOTOS: 413,
    ErrorCode.INVALID_PHOTO: 415,
    ErrorCode.AGENT_FAILURE: 502,
}
VALIDATION_ERROR_CODE = "validation_error"
HTTP_ERROR_CODE = "http_error"
INTERNAL_ERROR_CODE = "internal_error"
VALIDATION_MESSAGE = "Dados invalidos na requisicao."
INTERNAL_MESSAGE = "Erro interno. Tente novamente."


def error_response(status: int, code: str, message: str, **extra: object) -> JSONResponse:
    """Build the one error format every endpoint returns."""
    return JSONResponse(status_code=status, content={"code": code, "message": message, **extra})


async def handle_vencar_error(request: Request, error: VencarError) -> JSONResponse:
    """Translate an expected application failure into its HTTP status."""
    return error_response(STATUS_BY_CODE[error.code], error.code, error.message)


async def handle_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    """Report which request fields are invalid, without echoing their values."""
    fields = [".".join(str(part) for part in item["loc"]) for item in error.errors()]

    return error_response(422, VALIDATION_ERROR_CODE, VALIDATION_MESSAGE, fields=fields)


async def handle_http_error(request: Request, error: HTTPException) -> JSONResponse:
    """Keep framework errors, such as an unknown route, in the same format."""
    return error_response(error.status_code, HTTP_ERROR_CODE, str(error.detail))


async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """Log an unexpected failure and hide its details from the client."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=error)

    return error_response(500, INTERNAL_ERROR_CODE, INTERNAL_MESSAGE)


def register_error_handlers(app: FastAPI) -> None:
    """Make this module the only place that turns errors into HTTP responses."""
    app.add_exception_handler(VencarError, handle_vencar_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(HTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
