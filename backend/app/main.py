"""Punto de entrada de la API.

uvicorn --factory app.main:create_app
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Response, status
from pydantic import BaseModel

from app import __version__
from app.api import v1
from app.api.deps import SettingsDep
from app.api.errors import register_exception_handlers
from app.api.limits import BodySizeLimitMiddleware, max_body_bytes
from app.storage import CorruptDataError, ProjectRepository
from shared import ProviderMode, Settings, get_settings

logger = logging.getLogger("interiorai.backend")


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    mode: ProviderMode
    data_dir_writable: bool


def _data_dir_writable(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.W_OK)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    logging.basicConfig(
        level=settings.app.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    data_dir = settings.storage.data_dir
    try:
        await app.state.repository.init()
    except (OSError, CorruptDataError) as exc:
        logger.error("No se puede inicializar el directorio de datos %s: %s", data_dir, exc)
    logger.info(
        "InteriorAI backend %s | modo IA: %s | datos: %s",
        __version__,
        settings.app.ai_provider_mode.value,
        data_dir.as_posix(),
    )
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="InteriorAI API",
        version=__version__,
        lifespan=_lifespan,
    )
    app.state.settings = settings = settings or get_settings()
    app.state.repository = ProjectRepository(settings.storage.data_dir)

    app.add_middleware(
        BodySizeLimitMiddleware,
        max_body_bytes=max_body_bytes(settings.storage.max_upload_bytes),
    )
    register_exception_handlers(app)
    app.include_router(v1.router)

    @app.get("/health", response_model=HealthResponse, tags=["sistema"])
    async def health(settings: SettingsDep, response: Response) -> HealthResponse:
        writable = _data_dir_writable(settings.storage.data_dir)
        if not writable:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="ok" if writable else "degraded",
            version=__version__,
            mode=settings.app.ai_provider_mode,
            data_dir_writable=writable,
        )

    return app
