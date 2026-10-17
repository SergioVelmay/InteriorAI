"""Traducción de errores de dominio a respuestas HTTP (`{"detail": ...}` en español)."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.uploads import UploadError
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
