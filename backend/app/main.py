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
from app.telemetry import create_metered_client, load_pricing
from app.telemetry.middleware import RequestIdMiddleware
from shared import ProviderMode, Settings, get_settings
from shared.settings import legacy_env_warning

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
    await app.state.foundry.aclose()


DESCRIPTION = """API REST de InteriorAI: proyectos, referencias analizadas (receta y ficha),
bocetos, composición (auditoría y retoque), render final y costes de la IA.

Es la única vía de escritura en `data/` y de llamada a la IA (Azure AI Foundry o simulación).
Cada respuesta lleva la cabecera `X-Request-ID`; las que llaman a la IA devuelven además su
coste estimado (`cost_eur`). Documentación: https://sergiovelmay.github.io/InteriorAI/"""

# Grupos de endpoints del Swagger (Paso 35), en el orden del flujo de trabajo.
OPENAPI_TAGS = [
    {"name": "sistema", "description": "Estado del backend."},
    {"name": "proyectos", "description": "Crear, consultar, editar y mover a la papelera."},
    {"name": "assets", "description": "Imágenes del proyecto: subir referencias y descargar."},
    {"name": "catálogos", "description": "Valores admitidos (tipos de imagen)."},
    {"name": "pipelines", "description": "Análisis de referencias (receta) y su ficha."},
    {"name": "renders", "description": "Bocetos, composición, render final, selección, "
                                       "auditoría y retoque."},
    {"name": "costes", "description": "Gasto de la IA, avisos, coste de una cadena y precios."},
]  # fmt: skip


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="InteriorAI API",
        version=__version__,
        description=DESCRIPTION,
        contact={"name": "InteriorAI", "url": "https://github.com/SergioVelmay/InteriorAI"},
        license_info={"name": "MIT", "identifier": "MIT"},
        openapi_tags=OPENAPI_TAGS,
        lifespan=_lifespan,
    )
    app.state.settings = settings = settings or get_settings()
    if warning := legacy_env_warning(settings.legacy_env):
        logger.warning(warning)  # Paso 26: nombres anteriores de los roles en el `.env`
    app.state.repository = ProjectRepository(settings.storage.data_dir)
    app.state.foundry = create_metered_client(
        settings, app.state.repository, load_pricing(settings.storage.pricing_file)
    )

    app.add_middleware(
        BodySizeLimitMiddleware,
        max_body_bytes=max_body_bytes(settings.storage.max_upload_bytes),
    )
    app.add_middleware(RequestIdMiddleware)  # el último añadido es el más externo
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
