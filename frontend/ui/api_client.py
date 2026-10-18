"""Cliente asíncrono de la API del backend (única vía de escritura del frontend).

Tipado con los modelos de `shared`; cada petición lleva un `X-Request-ID` con prefijo `ui-`
para distinguir en la telemetría las acciones hechas desde la interfaz.
"""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel

from shared.models import (
    Asset,
    AssetKind,
    ProjectCreate,
    ProjectMetadata,
    ProjectSummary,
    ProjectUpdate,
    ReferenceAnalysis,
)

DEFAULT_TIMEOUT_S = 30
AI_TIMEOUT_S = 600  # llamadas que invocan a la IA (indexación, brief, renders)


class ApiError(Exception):
    """Error devuelto por la API (`detail` en español) o backend inalcanzable."""

    def __init__(self, status_code: int | None, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class Health(BaseModel):
    status: str
    version: str
    mode: str
    data_dir_writable: bool


def new_request_id() -> str:
    return f"ui-{uuid.uuid4().hex[:24]}"


def _detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        detail = None
    if isinstance(detail, list):  # errores de validación de FastAPI
        return "; ".join(str(item.get("msg", item)) for item in detail)
    return str(detail or f"Error {response.status_code} del backend")


class BackendClient:
    def __init__(
        self,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout_s = timeout_s

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {"X-Request-ID": new_request_id()}
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self._timeout_s, transport=self._transport
            ) as client:
                response = await client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(None, "No se puede conectar con el backend") from exc
        if response.status_code >= 400:
            raise ApiError(response.status_code, _detail(response))
        return response

    # --- Sistema y catálogos ------------------------------------------------------------

    async def health(self) -> Health:
        return Health.model_validate((await self._request("GET", "/health")).json())

    async def space_types(self) -> list[tuple[str, str]]:
        """[(etiqueta, valor)], el formato de `choices` de Gradio."""
        items = (await self._request("GET", "/api/v1/space-types")).json()
        return [(item["label"], item["value"]) for item in items]

    # --- Proyectos ------------------------------------------------------------------------

    async def list_projects(self) -> list[ProjectSummary]:
        items = (await self._request("GET", "/api/v1/projects")).json()
        return [ProjectSummary.model_validate(item) for item in items]

    async def get_project(self, project_id: UUID | str) -> ProjectMetadata:
        response = await self._request("GET", f"/api/v1/projects/{project_id}")
        return ProjectMetadata.model_validate(response.json())

    async def create_project(self, data: ProjectCreate) -> ProjectMetadata:
        response = await self._request(
            "POST", "/api/v1/projects", json=data.model_dump(mode="json")
        )
        return ProjectMetadata.model_validate(response.json())

    async def update_project(
        self, project_id: UUID | str, changes: ProjectUpdate
    ) -> ProjectMetadata:
        response = await self._request(
            "PATCH",
            f"/api/v1/projects/{project_id}",
            json=changes.model_dump(mode="json", exclude_unset=True),
        )
        return ProjectMetadata.model_validate(response.json())

    async def delete_project(self, project_id: UUID | str) -> None:
        await self._request("DELETE", f"/api/v1/projects/{project_id}")

    async def project_costs(self, project_id: UUID | str) -> dict[str, Any]:
        response = await self._request(
            "GET", f"/api/v1/projects/{project_id}/costs", params={"limit": 0}
        )
        return response.json()

    # --- Assets ---------------------------------------------------------------------------

    async def list_assets(
        self, project_id: UUID | str, kind: AssetKind | None = None
    ) -> list[Asset]:
        params = {"kind": kind.value} if kind else None
        response = await self._request(
            "GET", f"/api/v1/projects/{project_id}/assets", params=params
        )
        return [Asset.model_validate(item) for item in response.json()]

    async def upload_asset(
        self,
        project_id: UUID | str,
        kind: AssetKind,
        filename: str,
        content: bytes,
        description: str = "",
    ) -> Asset:
        response = await self._request(
            "POST",
            f"/api/v1/projects/{project_id}/assets/{kind.value}",
            files={"file": (filename, content)},
            data={"description": description},
        )
        return Asset.model_validate(response.json())

    async def update_asset_note(
        self, project_id: UUID | str, asset_id: UUID | str, note: str
    ) -> Asset:
        response = await self._request(
            "PATCH",
            f"/api/v1/projects/{project_id}/assets/{asset_id}",
            json={"description": note},
        )
        return Asset.model_validate(response.json())

    async def delete_asset(self, project_id: UUID | str, asset_id: UUID | str) -> None:
        await self._request("DELETE", f"/api/v1/projects/{project_id}/assets/{asset_id}")

    async def index_references(self, project_id: UUID | str, force: bool = False) -> dict[str, Any]:
        """CONTEXT_MANAGER: llama a la IA (coste en modo azure)."""
        response = await self._request(
            "POST",
            f"/api/v1/projects/{project_id}/references/index",
            json={"force": force},
            timeout=AI_TIMEOUT_S,
        )
        return response.json()

    async def validate_analysis(
        self, project_id: UUID | str, asset_id: UUID | str, analysis: ReferenceAnalysis
    ) -> Asset:
        response = await self._request(
            "PUT",
            f"/api/v1/projects/{project_id}/assets/{asset_id}/analysis",
            json=analysis.model_dump(mode="json"),
        )
        return Asset.model_validate(response.json())
