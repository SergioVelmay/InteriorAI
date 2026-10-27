"""GEOMETRY_AUDITOR: compara una imagen generada con las referencias del espacio.

A demanda (es el rol más caro): el informe se guarda en el render y no bloquea la selección.
Desde el Paso 23 (B-046) se audita el boceto seleccionado frente a TODAS las referencias activas
con perspectiva o geometría marcadas (ninguna, una o varias), con lo marcado en las fichas como
lista de comprobación; sus correcciones alimentan la composición.
"""

from __future__ import annotations

import json
from uuid import UUID

from pydantic import ValidationError

from app.foundry import FoundryClient, TextRequest
from app.pipelines.errors import PipelineError, PipelineInputError
from app.pipelines.images import prepare_image
from app.pipelines.prompts import load_prompt
from app.pipelines.renders import RenderNotFoundError
from app.pipelines.schemas import strict_schema
from app.pipelines.sources import active_references, geometric_references
from app.storage import ProjectRepository
from app.telemetry import current_request_id
from shared.models import (
    Asset,
    AuditReport,
    ProjectMetadata,
    RenderAudit,
    RenderRecord,
    RenderStage,
)
from shared.roles import Role

AUDIT_MAX_SIDE_PX = 1_536  # cotas legibles sin disparar los tokens de imagen
MAX_OUTPUT_TOKENS = 12_000  # razonamiento `max`: tope de coste por auditoría (~0,55 €)
SCHEMA = strict_schema(AuditReport)
AUDITABLE = frozenset({RenderStage.DRAFT, RenderStage.COMPOSITION, RenderStage.FINAL})


def _context(
    project: ProjectMetadata,
    render: RenderRecord,
    references: list[Asset],
    notes: str,
) -> str:
    """Lo que debe cumplir la imagen: lo marcado en las fichas y el prompt con que se generó."""
    validated = [  # lo marcado en las referencias activas (B-030)
        {
            "referencia": a.original_name,
            "seleccion": {
                group: [e.model_dump(mode="json") for e in elements]
                for group, elements in a.sheet.selected_elements().items()  # type: ignore[union-attr]
            },
        }
        for a in active_references(project)
    ]
    images = [
        f"- Imagen {i}: referencia del espacio — «{a.original_name}»"
        for i, a in enumerate(references, start=1)
    ]
    images.append(f"- Imagen {len(references) + 1}: imagen auditada")
    sections = [
        f"## Imagen auditada: {render.stage.label}",
        "## Imágenes (en este orden)",
        "\n".join(images),
        "## Lo marcado en las fichas del usuario",
        json.dumps(validated, ensure_ascii=False, indent=2) if validated else "(ninguna)",
        "## Prompt con el que se generó la imagen auditada",
        render.prompt,
    ]
    if notes.strip():
        sections += ["## Observaciones del usuario", notes.strip()]
    return "\n\n".join(sections)


async def audit_render(
    repo: ProjectRepository,
    client: FoundryClient,
    project_id: UUID,
    render_id: UUID,
    reasoning_effort: str,
    notes: str = "",
) -> tuple[RenderRecord, RenderAudit]:
    project = await repo.get(project_id)
    render = next((r for r in project.renders if r.id == render_id), None)
    if render is None:
        raise RenderNotFoundError(str(render_id))
    if render.stage not in AUDITABLE:
        raise PipelineInputError("Esta imagen no se puede auditar")
    references = geometric_references(project)
    prompt = load_prompt("auditor_espacio")
    images = [
        await prepare_image(await repo.read_asset_bytes(project.id, asset_id), AUDIT_MAX_SIDE_PX)
        for asset_id in (*(a.id for a in references), render.id)
    ]
    result = await client.complete_text(
        Role.GEOMETRY_AUDITOR,
        TextRequest(
            instructions=prompt.text,
            input=_context(project, render, references, notes),
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
        reference_asset_ids=[a.id for a in references],
        notes=notes.strip(),
        deployment=deployment_name(Role.GEOMETRY_AUDITOR) if deployment_name else result.deployment,
        reasoning_effort=reasoning_effort,
        prompt_version=prompt.version,
        request_id=current_request_id(),
        cost_eur=estimate(Role.GEOMETRY_AUDITOR, result.usage) if estimate else None,
    )

    def change(metadata: ProjectMetadata) -> tuple[ProjectMetadata, RenderRecord]:
        renders = list(metadata.renders)
        for i, current in enumerate(renders):
            if current.id == render_id:
                renders[i] = current.model_copy(update={"audits": [*current.audits, audit]})
                return metadata.model_copy(update={"renders": renders}), renders[i]
        raise RenderNotFoundError(str(render_id))

    return await repo.mutate(project_id, change), audit
