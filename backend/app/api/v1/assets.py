"""Assets de un proyecto: planos, referencias y capturas de SketchUp."""

import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import RepositoryDep, SettingsDep
from app.api.uploads import UploadError, UploadKind, decode_base64, inspect_upload, read_upload
from app.storage import AssetNotFoundError, ProjectRepository
from shared.models import Asset, AssetKind, ProjectMetadata

router = APIRouter(prefix="/projects/{project_id}/assets", tags=["assets"])

AllowDuplicate = Annotated[
    bool, Query(description="Permite subir un archivo idéntico a uno ya existente")
]


class Base64Upload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255, examples=["plano_salon.png"])
    data_base64: str = Field(
        min_length=1,
        description="Contenido en Base64; admite el prefijo `data:<mime>;base64,`",
    )
    description: str = Field(default="", max_length=2_000, examples=["Sofá 285 x 160 x 87 cm"])


class AssetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(max_length=2_000, description="Nota del usuario (p. ej. medidas)")


async def _store(
    repo: ProjectRepository,
    project_id: UUID,
    kind: UploadKind,
    content: bytes,
    filename: str,
    allow_duplicate: bool,
    description: str = "",
) -> Asset:
    existing = await repo.list_assets(project_id)  # 404 antes de procesar si no existe
    inspected = await inspect_upload(content, kind.asset_kind)
    if not allow_duplicate:
        sha256 = hashlib.sha256(content).hexdigest()
        duplicate = next((a for a in existing if a.sha256 == sha256), None)
        if duplicate is not None:
            raise UploadError(
                status.HTTP_409_CONFLICT,
                f"Este archivo ya existe en el proyecto como '{duplicate.original_name}'",
                extra={"existing_asset_id": str(duplicate.id)},
            )
    return await repo.add_asset(
        project_id,
        kind.asset_kind,
        content,
        filename,
        inspected.mime_type,
        inspected.width_px,
        inspected.height_px,
        description,
    )


def _set_location(request: Request, response: Response, project_id: UUID, asset: Asset) -> None:
    response.headers["Location"] = str(
        request.url_for("get_asset", project_id=project_id, asset_id=asset.id)
    )


@router.post("/{kind}", status_code=status.HTTP_201_CREATED, response_model=Asset)
async def upload_asset(
    project_id: UUID,
    kind: UploadKind,
    file: Annotated[UploadFile, File(description="Imagen PNG, JPEG o WebP")],
    repo: RepositoryDep,
    settings: SettingsDep,
    request: Request,
    response: Response,
    allow_duplicate: AllowDuplicate = False,
    description: Annotated[str, Form(max_length=2_000)] = "",
) -> Asset:
    """Subida multipart. El tipo real se detecta por el contenido, no por la extensión."""
    content = await read_upload(file, settings.storage.max_upload_bytes)
    asset = await _store(
        repo, project_id, kind, content, file.filename or "archivo", allow_duplicate, description
    )
    _set_location(request, response, project_id, asset)
    return asset


@router.post("/{kind}/base64", status_code=status.HTTP_201_CREATED, response_model=Asset)
async def upload_asset_base64(
    project_id: UUID,
    kind: UploadKind,
    body: Base64Upload,
    repo: RepositoryDep,
    settings: SettingsDep,
    request: Request,
    response: Response,
    allow_duplicate: AllowDuplicate = False,
) -> Asset:
    """Subida en JSON con el contenido en Base64."""
    content = decode_base64(body.data_base64, settings.storage.max_upload_bytes)
    asset = await _store(
        repo, project_id, kind, content, body.filename, allow_duplicate, body.description
    )
    _set_location(request, response, project_id, asset)
    return asset


@router.get("", response_model=list[Asset])
async def list_assets(
    project_id: UUID, repo: RepositoryDep, kind: AssetKind | None = None
) -> list[Asset]:
    return await repo.list_assets(project_id, kind)


@router.get("/{asset_id}", response_model=Asset, name="get_asset")
async def get_asset(project_id: UUID, asset_id: UUID, repo: RepositoryDep) -> Asset:
    return await repo.get_asset(project_id, asset_id)


@router.get("/{asset_id}/content", response_class=FileResponse)
async def download_asset(project_id: UUID, asset_id: UUID, repo: RepositoryDep) -> FileResponse:
    asset = await repo.get_asset(project_id, asset_id)
    return FileResponse(
        await repo.asset_path(project_id, asset_id),
        media_type=asset.mime_type,
        filename=asset.original_name,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"},
    )


@router.patch("/{asset_id}", response_model=Asset)
async def update_asset(
    project_id: UUID, asset_id: UUID, body: AssetUpdate, repo: RepositoryDep
) -> Asset:
    """Actualiza la nota del usuario sobre el asset (se usa al indexar y en el brief)."""

    def change(metadata: ProjectMetadata) -> tuple[ProjectMetadata, Asset]:
        assets = list(metadata.assets)
        for i, asset in enumerate(assets):
            if asset.id == asset_id:
                assets[i] = asset.model_copy(update={"description": body.description.strip()})
                return metadata.model_copy(update={"assets": assets}), assets[i]
        raise AssetNotFoundError(str(asset_id))

    return await repo.mutate(project_id, change)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(project_id: UUID, asset_id: UUID, repo: RepositoryDep) -> Response:
    """Borrado suave: el archivo se mueve a `data/.papelera/{proyecto}/`."""
    await repo.remove_asset(project_id, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
