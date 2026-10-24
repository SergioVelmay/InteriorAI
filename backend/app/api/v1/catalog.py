"""Catálogos estáticos para la interfaz (tipos de asset)."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.uploads import ACCEPTED_TYPES, UploadKind
from shared.models import AssetKind

router = APIRouter(tags=["catálogos"])


class AssetKindOut(BaseModel):
    value: AssetKind
    label: str
    folder: str
    uploadable: bool
    accepted_mime_types: list[str]


@router.get("/asset-kinds", response_model=list[AssetKindOut])
async def list_asset_kinds() -> list[AssetKindOut]:
    uploadable = {k.asset_kind for k in UploadKind}
    return [
        AssetKindOut(
            value=k,
            label=k.label,
            folder=k.folder,
            uploadable=k in uploadable,
            accepted_mime_types=sorted(ACCEPTED_TYPES[k]),
        )
        for k in AssetKind
    ]
