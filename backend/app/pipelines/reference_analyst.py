"""REFERENCE_ANALYST: receta de cada imagen de referencia y su ficha (B-029 y B-030).

Cada imagen se analiza al subirla, de una en una, orientada por las notas del usuario. La
receta agrupa los «ingredientes» útiles para el diseño; la ficha guarda qué elementos ha marcado
el usuario (de entrada, los que piden las notas). Solo las referencias activas (con algo
marcado) se usan en el diseño.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from uuid import UUID

from pydantic import ValidationError

from app.foundry import FoundryClient, FoundryError, TextRequest
from app.pipelines.errors import PipelineError, PipelineInputError
from app.pipelines.images import VISION_MIME_TYPES, prepare_image
from app.pipelines.prompts import load_prompt
from app.pipelines.schemas import strict_schema
from app.storage import AssetNotFoundError, ProjectRepository
from app.telemetry import current_request_id
from shared.models import (
    Asset,
    AssetKind,
    ProjectMetadata,
    ReferenceRecipe,
    ReferenceSheet,
    utc_now,
)
from shared.roles import Role

logger = logging.getLogger("interiorai.pipelines")

MAX_CONCURRENCY = 3  # solo para el reanálisis en bloque; al subir se analiza de una en una
MAX_OUTPUT_TOKENS = 8_000  # la receta es larga y el despliegue puede razonar
SCHEMA = strict_schema(ReferenceRecipe)


# Primer análisis de las capturas y planos de la v1 (Paso 21, decisión del usuario): se añade a
# sus notas lo que aportaban, para que su papel anterior quede marcado en la ficha.
LEGACY_NOTES = {
    "captura_sketchup": "Quédate con el punto de vista, la perspectiva y la geometría del espacio.",
    "plano": "Quédate con las medidas y la distribución.",
}


@dataclass
class IndexResult:
    indexed: list[Asset] = field(default_factory=list)
    skipped: list[UUID] = field(default_factory=list)
    failed: list[tuple[UUID, str]] = field(default_factory=list)


def _input_text(project: ProjectMetadata, asset: Asset) -> str:
    notes = asset.description or "(sin notas)"
    return (
        f"Proyecto: {project.name}.\n"
        f"Archivo: {asset.original_name}\n"
        f"Notas del usuario sobre esta imagen: {notes}\n"
        "Analiza la imagen adjunta y devuelve su receta."
    )


def _reference(project: ProjectMetadata, asset_id: UUID) -> Asset:
    asset = next((a for a in project.assets if a.id == asset_id), None)
    if asset is None:
        raise AssetNotFoundError(str(asset_id))
    if asset.kind is not AssetKind.REFERENCIA:
        raise PipelineInputError("Solo las referencias tienen receta y ficha")
    if asset.mime_type not in VISION_MIME_TYPES:
        raise PipelineInputError(f"'{asset.original_name}' no es una imagen analizable")
    return asset


async def analyze_reference(
    client: FoundryClient, repo: ProjectRepository, project: ProjectMetadata, asset: Asset
) -> ReferenceSheet:
    """Receta de la imagen y ficha inicial: marcado lo que piden las notas."""
    prompt = load_prompt("reference_analyst")
    image = await prepare_image(await repo.read_asset_bytes(project.id, asset.id))
    result = await client.complete_text(
        Role.REFERENCE_ANALYST,
        TextRequest(
            instructions=prompt.text,
            input=_input_text(project, asset),
            images=[image],
            json_schema=SCHEMA,
            schema_name="receta_referencia",
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
    )
    try:
        recipe = ReferenceRecipe.model_validate(result.data)
    except ValidationError as exc:
        raise PipelineError("La receta devuelta por el modelo no cumple el esquema") from exc
    return ReferenceSheet(
        recipe=recipe,
        selected=[element_id for element_id, e in recipe.elements() if e.selected],
        notes=asset.description,
        prompt_version=prompt.version,
        request_id=current_request_id(),
        # El despliegue configurado (el cliente con telemetría lo conoce también en mock).
        deployment=(
            client.deployment_name(Role.REFERENCE_ANALYST)  # type: ignore[attr-defined]
            if hasattr(client, "deployment_name")
            else result.deployment
        ),
    )


async def _store_sheet(
    repo: ProjectRepository, project_id: UUID, asset_id: UUID, sheet: ReferenceSheet
) -> Asset:
    def change(metadata: ProjectMetadata) -> tuple[ProjectMetadata, Asset]:
        assets = list(metadata.assets)
        for i, asset in enumerate(assets):
            if asset.id == asset_id:
                assets[i] = asset.model_copy(update={"sheet": sheet})
                return metadata.model_copy(update={"assets": assets}), assets[i]
        raise PipelineInputError(f"La referencia {asset_id} ya no existe")

    return await repo.mutate(project_id, change)


async def analyze_asset(
    repo: ProjectRepository,
    client: FoundryClient,
    project_id: UUID,
    asset_id: UUID,
    notes: str | None = None,
) -> Asset:
    """Analiza (o vuelve a analizar) una referencia; `notes` sustituye antes a sus notas. La
    ficha anterior se reemplaza por la nueva, con lo que piden las notas ya marcado."""
    project = await repo.get(project_id)
    asset = _reference(project, asset_id)
    if notes is not None and notes.strip() != asset.description:

        def set_notes(metadata: ProjectMetadata) -> tuple[ProjectMetadata, Asset]:
            assets = list(metadata.assets)
            for i, item in enumerate(assets):
                if item.id == asset_id:
                    assets[i] = item.model_copy(update={"description": notes.strip()})
                    return metadata.model_copy(update={"assets": assets}), assets[i]
            raise AssetNotFoundError(str(asset_id))

        asset = await repo.mutate(project_id, set_notes)
    sheet = await analyze_reference(client, repo, project, asset)
    return await _store_sheet(repo, project_id, asset_id, sheet)


async def index_references(
    repo: ProjectRepository,
    client: FoundryClient,
    project_id: UUID,
    asset_ids: list[UUID] | None = None,
    force: bool = False,
) -> IndexResult:
    """Analiza en bloque las referencias sin receta (o `asset_ids`); `force` vuelve a
    analizar también las que ya la tienen (p. ej. tras cambiar el prompt)."""
    project = await repo.get(project_id)
    references = [
        a
        for a in project.assets
        if a.kind is AssetKind.REFERENCIA and a.mime_type in VISION_MIME_TYPES
    ]
    if asset_ids is not None:
        wanted = set(asset_ids)
        unknown = wanted - {a.id for a in references}
        if unknown:
            raise PipelineInputError(
                "No son referencias de este proyecto: " + ", ".join(sorted(map(str, unknown)))
            )
        references = [a for a in references if a.id in wanted]
    if not references:
        raise PipelineInputError("El proyecto no tiene referencias que analizar")

    result = IndexResult()
    pending = []
    for asset in references:
        if asset.sheet is not None and not force:
            result.skipped.append(asset.id)
        else:
            pending.append(asset)

    pending = [await _with_legacy_notes(repo, project_id, a) for a in pending]
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def run(asset: Asset) -> None:
        async with semaphore:
            try:
                sheet = await analyze_reference(client, repo, project, asset)
                result.indexed.append(await _store_sheet(repo, project.id, asset.id, sheet))
            except (FoundryError, PipelineError) as exc:
                logger.warning("No se pudo analizar la referencia %s: %s", asset.id, exc)
                result.failed.append((asset.id, f"{type(exc).__name__}: {exc}"))

    await asyncio.gather(*(run(asset) for asset in pending))
    return result


async def _with_legacy_notes(repo: ProjectRepository, project_id: UUID, asset: Asset) -> Asset:
    """Captura o plano de la v1 sin receta: añade a sus notas el papel que tenía."""
    hint = LEGACY_NOTES.get(asset.legacy_kind or "")
    if asset.sheet is not None or hint is None or hint in asset.description:
        return asset
    notes = f"{asset.description}\n{hint}".strip()

    def change(metadata: ProjectMetadata) -> tuple[ProjectMetadata, Asset]:
        assets = list(metadata.assets)
        for i, item in enumerate(assets):
            if item.id == asset.id:
                assets[i] = item.model_copy(update={"description": notes})
                return metadata.model_copy(update={"assets": assets}), assets[i]
        raise AssetNotFoundError(str(asset.id))

    return await repo.mutate(project_id, change)


async def save_sheet(
    repo: ProjectRepository, project_id: UUID, asset_id: UUID, selected: list[str]
) -> Asset:
    """El usuario guarda la ficha con los elementos que marca (vacía = referencia descartada,
    que se reactiva marcando algo)."""

    def change(metadata: ProjectMetadata) -> tuple[ProjectMetadata, Asset]:
        assets = list(metadata.assets)
        for i, asset in enumerate(assets):
            if asset.id != asset_id:
                continue
            if asset.kind is not AssetKind.REFERENCIA or asset.sheet is None:
                raise PipelineInputError("Esta imagen aún no tiene receta: analízala antes")
            valid = {element_id for element_id, _ in asset.sheet.recipe.elements()}
            if unknown := sorted(set(selected) - valid):
                raise PipelineInputError(
                    "Elementos que no están en la receta: " + ", ".join(unknown)
                )
            ordered = [element_id for element_id, _ in asset.sheet.recipe.elements()
                       if element_id in set(selected)]  # fmt: skip
            sheet = asset.sheet.model_copy(update={"selected": ordered, "saved_at": utc_now()})
            assets[i] = asset.model_copy(update={"sheet": sheet})
            return metadata.model_copy(update={"assets": assets}), assets[i]
        raise AssetNotFoundError(str(asset_id))

    return await repo.mutate(project_id, change)
