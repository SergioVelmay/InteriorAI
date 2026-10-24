"""CONTEXT_MANAGER: indexa las referencias del proyecto en fichas estructuradas."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from uuid import UUID

from pydantic import ValidationError

from app.foundry import FoundryClient, FoundryError, TextRequest
from app.pipelines.errors import PipelineError, PipelineInputError
from app.pipelines.images import prepare_image
from app.pipelines.prompts import load_prompt
from app.pipelines.schemas import strict_schema
from app.storage import AssetNotFoundError, ProjectRepository
from app.telemetry import current_request_id
from shared.models import (
    Asset,
    AssetAnalysis,
    AssetKind,
    ProjectMetadata,
    ReferenceAnalysis,
    utc_now,
)
from shared.roles import Role

logger = logging.getLogger("interiorai.pipelines")

MAX_CONCURRENCY = 3
MAX_OUTPUT_TOKENS = 2_000  # el despliegue razona por defecto: margen para el razonamiento
SCHEMA = strict_schema(ReferenceAnalysis)


@dataclass
class IndexResult:
    indexed: list[Asset] = field(default_factory=list)
    skipped: list[UUID] = field(default_factory=list)
    failed: list[tuple[UUID, str]] = field(default_factory=list)


def _input_text(project: ProjectMetadata, asset: Asset) -> str:
    note = asset.description or "(sin nota)"
    return (
        f"Proyecto: {project.name} ({project.space_type.label}).\n"
        f"Archivo: {asset.original_name}\n"
        f"Nota del usuario sobre esta referencia: {note}\n"
        "Analiza la imagen adjunta y devuelve la ficha."
    )


async def analyze_reference(
    client: FoundryClient, repo: ProjectRepository, project: ProjectMetadata, asset: Asset
) -> AssetAnalysis:
    prompt = load_prompt("context_manager")
    image = await prepare_image(await repo.read_asset_bytes(project.id, asset.id))
    result = await client.complete_text(
        Role.CONTEXT_MANAGER,
        TextRequest(
            instructions=prompt.text,
            input=_input_text(project, asset),
            images=[image],
            json_schema=SCHEMA,
            schema_name="ficha_referencia",
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
    )
    try:
        analysis = ReferenceAnalysis.model_validate(result.data)
    except ValidationError as exc:
        raise PipelineError("La ficha devuelta por el modelo no cumple el esquema") from exc
    return AssetAnalysis(
        result=analysis, prompt_version=prompt.version, request_id=current_request_id()
    )


async def _save(
    repo: ProjectRepository, project_id: UUID, asset_id: UUID, analysis: AssetAnalysis
) -> Asset:
    def change(metadata: ProjectMetadata) -> tuple[ProjectMetadata, Asset]:
        assets = list(metadata.assets)
        for i, asset in enumerate(assets):
            if asset.id == asset_id:
                assets[i] = asset.model_copy(update={"analysis": analysis})
                return metadata.model_copy(update={"assets": assets}), assets[i]
        raise PipelineInputError(f"La referencia {asset_id} ya no existe")

    return await repo.mutate(project_id, change)


async def index_references(
    repo: ProjectRepository,
    client: FoundryClient,
    project_id: UUID,
    asset_ids: list[UUID] | None = None,
    force: bool = False,
) -> IndexResult:
    """Indexa las referencias pendientes (o `asset_ids`); `force` reindexa las ya analizadas."""
    project = await repo.get(project_id)
    references = [a for a in project.assets if a.kind is AssetKind.REFERENCIA]
    if asset_ids is not None:
        wanted = set(asset_ids)
        unknown = wanted - {a.id for a in references}
        if unknown:
            raise PipelineInputError(
                "No son referencias de este proyecto: " + ", ".join(sorted(map(str, unknown)))
            )
        references = [a for a in references if a.id in wanted]
    if not references:
        raise PipelineInputError("El proyecto no tiene referencias que indexar")

    result = IndexResult()
    pending = []
    for asset in references:
        if asset.analysis is not None and not force:
            result.skipped.append(asset.id)
        else:
            pending.append(asset)

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def run(asset: Asset) -> None:
        async with semaphore:
            try:
                analysis = await analyze_reference(client, repo, project, asset)
                result.indexed.append(await _save(repo, project.id, asset.id, analysis))
            except (FoundryError, PipelineError) as exc:
                logger.warning("No se pudo indexar la referencia %s: %s", asset.id, exc)
                result.failed.append((asset.id, f"{type(exc).__name__}: {exc}"))

    await asyncio.gather(*(run(asset) for asset in pending))
    return result


async def validate_analysis(
    repo: ProjectRepository, project_id: UUID, asset_id: UUID, corrected: ReferenceAnalysis
) -> Asset:
    """El usuario revisa o corrige la ficha: queda marcada como `validated`."""

    def change(metadata: ProjectMetadata) -> tuple[ProjectMetadata, Asset]:
        assets = list(metadata.assets)
        for i, asset in enumerate(assets):
            if asset.id != asset_id:
                continue
            if asset.kind is not AssetKind.REFERENCIA:
                raise PipelineInputError("Solo las referencias tienen ficha")
            now = utc_now()
            previous = asset.analysis
            analysis = AssetAnalysis(
                result=corrected,
                status="validated",
                prompt_version=previous.prompt_version if previous else None,
                analyzed_at=previous.analyzed_at if previous else now,
                validated_at=now,
                request_id=previous.request_id if previous else None,
            )
            assets[i] = asset.model_copy(update={"analysis": analysis})
            return metadata.model_copy(update={"assets": assets}), assets[i]
        raise AssetNotFoundError(str(asset_id))

    return await repo.mutate(project_id, change)
