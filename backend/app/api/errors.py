"""Traducción de errores de dominio a respuestas HTTP (`{"detail": ...}` en español)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.uploads import UploadError
from app.foundry import (
    FoundryContentFilterError,
    FoundryError,
    FoundryRateLimitError,
    FoundryTimeoutError,
    FoundryUnsupportedError,
)
from app.hitl import TransitionError
from app.pipelines.errors import PipelineError, PipelineInputError
from app.pipelines.renders import RenderNotFoundError
from app.storage import (
    AssetNotFoundError,
    CorruptDataError,
    InvalidPathError,
    ProjectNotFoundError,
)

logger = logging.getLogger("interiorai.api")


def _detail(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status_code)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProjectNotFoundError)
    async def _project_not_found(_: Request, __: ProjectNotFoundError) -> JSONResponse:
        return _detail(status.HTTP_404_NOT_FOUND, "Proyecto no encontrado")

    @app.exception_handler(AssetNotFoundError)
    async def _asset_not_found(_: Request, __: AssetNotFoundError) -> JSONResponse:
        return _detail(status.HTTP_404_NOT_FOUND, "Asset no encontrado")

    @app.exception_handler(InvalidPathError)
    async def _invalid_path(_: Request, exc: InvalidPathError) -> JSONResponse:
        return _detail(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))

    @app.exception_handler(CorruptDataError)
    async def _corrupt(request: Request, exc: CorruptDataError) -> JSONResponse:
        logger.error("Datos corruptos en %s %s: %s", request.method, request.url.path, exc)
        return _detail(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Los datos del proyecto están dañados; revisa los logs del backend",
        )

    @app.exception_handler(UploadError)
    async def _upload(_: Request, exc: UploadError) -> JSONResponse:
        return JSONResponse({"detail": exc.detail, **exc.extra}, status_code=exc.status_code)

    # Errores con mensaje propio en español: se devuelve el mensaje con su código HTTP.
    # Starlette resuelve por la jerarquía de clases (la más específica gana).
    for error_type, status_code in _MESSAGE_ERRORS.items():
        app.add_exception_handler(error_type, _message_handler(status_code))


def _message_handler(
    status_code: int,
) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        if status_code >= 500:
            logger.warning("%s en %s %s: %s", type(exc).__name__, request.method,
                           request.url.path, exc)  # fmt: skip
        return _detail(status_code, str(exc))

    return handler


_MESSAGE_ERRORS: dict[type[Exception], int] = {
    RenderNotFoundError: status.HTTP_404_NOT_FOUND,
    TransitionError: status.HTTP_409_CONFLICT,
    PipelineInputError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    PipelineError: status.HTTP_502_BAD_GATEWAY,
    FoundryUnsupportedError: status.HTTP_400_BAD_REQUEST,
    FoundryContentFilterError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    FoundryRateLimitError: status.HTTP_429_TOO_MANY_REQUESTS,
    FoundryTimeoutError: status.HTTP_504_GATEWAY_TIMEOUT,
    FoundryError: status.HTTP_502_BAD_GATEWAY,  # auth, 400 del proveedor, incompletas...
}
