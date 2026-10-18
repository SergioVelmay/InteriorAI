"""GEOMETRIC_AUDITOR: compara una composición o render final con la captura de SketchUp.

A demanda (es el rol más caro): el informe se guarda en el render y no bloquea la selección.
"""

from __future__ import annotations

import json
from uuid import UUID

from pydantic import ValidationError

from app.foundry import FoundryClient, TextRequest
from app.hitl.briefs import find_brief
from app.pipelines.errors import PipelineError, PipelineInputError
from app.pipelines.images import prepare_image
from app.pipelines.prompts import load_prompt
from app.pipelines.renders import RenderNotFoundError
from app.pipelines.schemas import strict_schema
from app.storage import ProjectRepository
from app.telemetry import current_request_id
from shared.models import (
    AssetKind,
    AuditReport,
    DesignBrief,
    ProjectMetadata,
    RenderAudit,
    RenderRecord,
    RenderStage,
)
from shared.roles import Role

AUDIT_MAX_SIDE_PX = 1_536  # cotas legibles sin disparar los tokens de imagen
MAX_OUTPUT_TOKENS = 12_000  # razonamiento `max`: tope de coste por auditoría (~0,55 €)
SCHEMA = strict_schema(AuditReport)
AUDITABLE = frozenset({RenderStage.COMPOSITION, RenderStage.FINAL})


def reference_asset_id(project: ProjectMetadata, render: RenderRecord) -> UUID:
    """Captura/plano de origen: se sigue la cadena de renders hasta la imagen subida."""
    renders = {r.id: r for r in project.renders}
    assets = {a.id: a for a in project.assets}
    current = render.input_asset_ids[0]
    while current in renders:
        current = renders[current].input_asset_ids[0]
    asset = assets.get(current)
    if asset is None or asset.kind not in {AssetKind.CAPTURA_SKETCHUP, AssetKind.PLANO}:
        raise PipelineInputError("No se encuentra la captura o el plano de origen del render")
    return current


def _context(project: ProjectMetadata, brief: DesignBrief, render: RenderRecord) -> str:
    content = brief.content
    validated = [
        {"referencia": a.original_name, "ficha": a.analysis.result.model_dump(mode="json")}
        for a in project.assets
        if a.kind is AssetKind.REFERENCIA and a.analysis and a.analysis.status == "validated"
    ]
    sections = [
        f"## Imagen auditada: {render.stage.label} (brief v{brief.version})",
        "## Restricciones espaciales del brief",
        "\n".join(f"- {c}" for c in content.spatial_constraints) or "(ninguna)",
        "## Mobiliario que debe respetarse con exactitud",
        json.dumps(
            [f.model_dump(mode="json") for f in content.furniture if f.keep_exact],
            ensure_ascii=False,
            indent=2,
        ),
        "## Materiales y paleta pedidos",
        "\n".join(f"- {m}" for m in [*content.materials, *content.palette]),
        "## Fichas validadas por el usuario",
        json.dumps(validated, ensure_ascii=False, indent=2) if validated else "(ninguna)",
        "## Prompt con el que se generó la imagen auditada",
        render.prompt,
    ]
    return "\n\n".join(sections)


async def audit_render(
    repo: ProjectRepository,
    client: FoundryClient,
    project_id: UUID,
    render_id: UUID,
    reasoning_effort: str,
) -> tuple[RenderRecord, RenderAudit]:
    project = await repo.get(project_id)
    render = next((r for r in project.renders if r.id == render_id), None)
    if render is None:
        raise RenderNotFoundError(str(render_id))
    if render.stage not in AUDITABLE:
        raise PipelineInputError("Solo se auditan composiciones y renders finales")
    brief = find_brief(project, render.brief_id)
    reference_id = reference_asset_id(project, render)
    prompt = load_prompt("geometric_auditor")

    images = [
        await prepare_image(await repo.read_asset_bytes(project.id, asset_id), AUDIT_MAX_SIDE_PX)
        for asset_id in (reference_id, render.id)
    ]
    result = await client.complete_text(
        Role.GEOMETRIC_AUDITOR,
        TextRequest(
            instructions=prompt.text,
            input=_context(project, brief, render),
            images=images,
            json_schema=SCHEMA,
            schema_name="auditoria",
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
    )
    try:
        report = AuditReport.model_validate(result.data)
    except ValidationError as exc:
        raise PipelineError("El informe del auditor no cumple el esquema") from exc

    estimate = getattr(client, "estimate", None)
    deployment_name = getattr(client, "deployment_name", None)
    audit = RenderAudit(
        report=report,
        reference_asset_id=reference_id,
        deployment=deployment_name(Role.GEOMETRIC_AUDITOR)
        if deployment_name
        else result.deployment,
        reasoning_effort=reasoning_effort,
        prompt_version=prompt.version,
        request_id=current_request_id(),
        cost_eur=estimate(Role.GEOMETRIC_AUDITOR, result.usage) if estimate else None,
    )

    def change(metadata: ProjectMetadata) -> tuple[ProjectMetadata, RenderRecord]:
        renders = list(metadata.renders)
        for i, current in enumerate(renders):
            if current.id == render_id:
                renders[i] = current.model_copy(update={"audits": [*current.audits, audit]})
                return metadata.model_copy(update={"renders": renders}), renders[i]
        raise RenderNotFoundError(str(render_id))

    return await repo.mutate(project_id, change), audit
