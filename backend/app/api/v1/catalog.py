"""Catálogos estáticos para la interfaz (tipos de espacio y de asset)."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.uploads import ACCEPTED_TYPES, UploadKind
from shared.models import AssetKind, SpaceType

router = APIRouter(tags=["catálogos"])


class SpaceTypeOut(BaseModel):
    value: SpaceType
    label: str


class AssetKindOut(BaseModel):
    value: AssetKind
    label: str
    folder: str
    uploadable: bool
    accepted_mime_types: list[str]


@router.get("/space-types", response_model=list[SpaceTypeOut])
async def list_space_types() -> list[SpaceTypeOut]:
    return [SpaceTypeOut(value=t, label=t.label) for t in SpaceType]


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
