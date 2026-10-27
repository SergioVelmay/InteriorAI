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
    RenderRecord,
    RenderStage,
)

DEFAULT_TIMEOUT_S = 30
AI_TIMEOUT_S = 600  # llamadas que invocan a la IA (análisis de referencias y renders)
AI_AUDIT_TIMEOUT_S = 1_000  # el backend espera hasta GEOMETRY_AUDITOR_TIMEOUT_S (900 s)


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
        """Gasto real del proyecto con sus llamadas (las 1000 últimas, el máximo de la API); sin
        las simuladas, como la pestaña Costes IA (B-031)."""
        response = await self._request(
            "GET", f"/api/v1/projects/{project_id}/costs",
            params={"limit": 1000, "include_simulated": False},
        )  # fmt: skip
        return response.json()

    async def costs(
        self, project_id: UUID | str | None, include_simulated: bool = False, limit: int = 1000
    ) -> dict[str, Any]:
        """Resumen de costes de un proyecto (o de todos si `project_id` es None)."""
        path = f"/api/v1/projects/{project_id}/costs" if project_id else "/api/v1/costs"
        params = {"limit": limit, "include_simulated": include_simulated}
        return (await self._request("GET", path, params=params)).json()

    async def cost_alerts(self) -> dict[str, Any] | None:
        """Avisos de gasto real por proyecto y total (B-021); None si no se pueden consultar:
        un aviso nunca debe impedir usar la app."""
        try:
            return (await self._request("GET", "/api/v1/costs/alerts")).json()
        except ApiError:
            return None

    async def pricing(self) -> dict[str, Any] | None:
        try:
            return (await self._request("GET", "/api/v1/pricing")).json()
        except ApiError as exc:
            if exc.status_code == 404:  # sin tabla de precios
                return None
            raise

    async def render_cost(self, project_id: UUID | str, render_id: UUID | str) -> dict[str, Any]:
        """Coste acumulado de la cadena que lleva a un render."""
        response = await self._request(
            "GET", f"/api/v1/projects/{project_id}/renders/{render_id}/cost"
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

    async def analyze_reference(
        self, project_id: UUID | str, asset_id: UUID | str, notes: str | None = None
    ) -> dict[str, Any]:
        """Receta de una referencia (coste en modo azure). Devuelve `{asset, cost_eur, …}`."""
        response = await self._request(
            "POST", f"/api/v1/projects/{project_id}/assets/{asset_id}/analyze",
            json={} if notes is None else {"notes": notes}, timeout=AI_TIMEOUT_S,
        )  # fmt: skip
        return response.json()

    async def save_sheet(
        self, project_id: UUID | str, asset_id: UUID | str, selected: list[str]
    ) -> Asset:
        """«Guardar ficha»: los elementos marcados (vacío = referencia descartada)."""
        response = await self._request(
            "PUT", f"/api/v1/projects/{project_id}/assets/{asset_id}/sheet",
            json={"selected": selected},
        )  # fmt: skip
        return Asset.model_validate(response.json())

    # --- Estudio (Paso 22: sin brief; el prompt se escribe en cada generación) -------------

    def _project(self, project_id: UUID | str) -> str:
        return f"/api/v1/projects/{project_id}"

    async def list_renders(
        self, project_id: UUID | str, stage: RenderStage | None = None
    ) -> list[RenderRecord]:
        params = {"stage": stage.value} if stage else None
        response = await self._request("GET", f"{self._project(project_id)}/renders", params=params)
        return [RenderRecord.model_validate(item) for item in response.json()]

    async def generate_renders(
        self, project_id: UUID | str, stage: RenderStage, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Boceto / composición / render final (coste en modo azure)."""
        path = {
            RenderStage.DRAFT: "drafts",
            RenderStage.COMPOSITION: "compositions",
            RenderStage.FINAL: "final",
        }[stage]
        response = await self._request(
            "POST", f"{self._project(project_id)}/renders/{path}", json=body, timeout=AI_TIMEOUT_S
        )
        return response.json()

    async def select_render(self, project_id: UUID | str, render_id: UUID | str) -> RenderRecord:
        response = await self._request(
            "POST", f"{self._project(project_id)}/renders/{render_id}/select"
        )
        return RenderRecord.model_validate(response.json())

    async def audit_render(
        self, project_id: UUID | str, render_id: UUID | str, notes: str = ""
    ) -> dict[str, Any]:
        """GEOMETRY_AUDITOR (el rol más caro), con las observaciones del usuario."""
        response = await self._request(
            "POST", f"{self._project(project_id)}/renders/{render_id}/audit",
            json={"notes": notes}, timeout=AI_AUDIT_TIMEOUT_S,
        )  # fmt: skip
        return response.json()

    async def inpaint_render(
        self,
        project_id: UUID | str,
        render_id: UUID | str,
        mask_png: bytes,
        instruction: str,
        **options: Any,
    ) -> dict[str, Any]:
        """Retoque de la zona pintada (coste en modo azure). Devuelve `{renders, cost_eur, …}`.

        `options`: `quality`, `extra_instructions`, `use_audit` y `audit_notes` (Paso 23).
        """
        data = {"instruction": instruction}
        data |= {k: str(v).lower() if isinstance(v, bool) else str(v)
                 for k, v in options.items() if v is not None}  # fmt: skip
        response = await self._request(
            "POST", f"{self._project(project_id)}/renders/{render_id}/inpaint",
            files={"mask": ("mascara.png", mask_png, "image/png")},
            data=data, timeout=AI_TIMEOUT_S,
        )  # fmt: skip
        return response.json()
