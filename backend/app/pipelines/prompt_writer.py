"""Prompt automático de cada generación (Paso 22: sustituye al brief de la v1).

Al pulsar «Generar» en cualquier etapa, el PROMPT_ARCHITECT escribe el prompt de ESA generación
con sus entradas reales: la descripción del proyecto, las imágenes que recibirá el modelo de
imagen (con su papel), lo marcado en las fichas de las referencias activas y las indicaciones
del usuario. Devuelve también lo que ha entendido y sus dudas, que se guardan con cada imagen.

Paso 32 (B-054, B-094 a B-097): como es barato, recibe más contexto (el resumen del análisis de
cada referencia, el historial de la imagen de partida y las generaciones anteriores de la etapa,
para resolver sus dudas), las imágenes con más detalle y margen de sobra para razonar; el prompt
de sistema de cada etapa se completa con unos criterios comunes (`prompt_criterios.md`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from pydantic import ValidationError

from app.foundry import FoundryClient, InputImage, TextRequest
from app.pipelines.errors import PipelineError
from app.pipelines.images import prepare_image
from app.pipelines.prompts import load_prompt
from app.pipelines.schemas import strict_schema
from app.storage import ProjectRepository
from shared.models import (
    RECIPE_GROUPS,
    Asset,
    ProjectMetadata,
    RecipeElement,
    RenderRecord,
    RenderStage,
    RenderStatus,
    StagePrompt,
)
from shared.roles import Role

SCHEMA = strict_schema(StagePrompt)
# Incluye el razonamiento: con `high`, un prompt de bocetos razonó 12 638 tokens (Paso 32); con el
# tope anterior (6 000) la respuesta quedaba incompleta y la generación fallaba.
MAX_OUTPUT_TOKENS = 32_000
# El escritor ve las imágenes para describirlas (no para copiarlas), con detalle alto para leer
# cotas y rótulos.
WRITER_MAX_SIDE_PX = 1_536
WRITER_IMAGE_DETAIL = "high"
CRITERIA_FILE = "prompt_criterios"  # criterios comunes a las tres etapas
HISTORY_MAX = 12  # imágenes del historial de la imagen de partida
PROMPT_FILES = {
    RenderStage.DRAFT: "prompt_bocetos",
    RenderStage.COMPOSITION: "prompt_composicion",
    RenderStage.FINAL: "prompt_render_final",
}


@dataclass(frozen=True)
class InputRole:
    """Una imagen que recibirá el modelo de imagen y su papel (p. ej. «imagen base»)."""

    asset: Asset
    role: str


@dataclass(frozen=True)
class WrittenPrompt:
    prompt: StagePrompt
    version: str  # versión del prompt de sistema


def _element(element: RecipeElement) -> dict:
    entry: dict = {"elemento": element.label}
    if element.detail:
        entry["detalle"] = element.detail
    if element.dimensions_source != "ninguna":
        entry["medidas_cm"] = element.dimensions_cm.model_dump(mode="json")
        entry["origen_medidas"] = element.dimensions_source  # «estimada» = aproximada
    return entry


def references_section(references: list[Asset], numbers: dict) -> list[dict]:
    """Lo marcado en cada referencia activa, con su número de imagen si se envía. De las que se
    envían como imagen, también lo NO marcado (`ignorar`): el modelo de imagen ve la imagen
    entera y el prompt debe decirle qué no tomar (Paso 28, B-068)."""
    entries = []
    for asset in references:
        if asset.sheet is None:
            continue
        entry: dict = {"archivo": asset.original_name}
        if asset.id in numbers:
            entry["imagen"] = numbers[asset.id]
        if asset.sheet.recipe.summary:
            entry["resumen_analisis"] = asset.sheet.recipe.summary
        if asset.description:
            entry["notas_usuario"] = asset.description
        entry["seleccion"] = {
            RECIPE_GROUPS[group]: [_element(e) for e in elements]
            for group, elements in asset.sheet.selected_elements().items()
        }
        if asset.id in numbers:
            entry["ignorar"] = {
                RECIPE_GROUPS[group]: [e.label for e in elements]
                for group, elements in asset.sheet.unselected_elements().items()
            }
        entries.append(entry)
    return entries


def _label(render: RenderRecord) -> str:
    return f"{render.stage.label} {render.id.hex[:8]}"


def _source_of(render: RenderRecord) -> UUID | None:
    """De qué imagen viene: la retocada, la repetida («Otra versión») o la de la etapa anterior."""
    if render.inpaint is not None:
        return render.inpaint.source_render_id
    return render.variant_of_id or render.parent_render_id


def history_section(project: ProjectMetadata, inputs: list[InputRole]) -> list[dict]:
    """Cómo se llegó a la imagen de partida (B-095), de la más antigua a ella: lo que se
    pretendía en cada etapa y los retoques que pidió el usuario. Vacío si no parte de un render."""
    renders = {r.id: r for r in project.renders}
    current = renders.get(inputs[0].asset.id) if inputs else None
    chain: list[RenderRecord] = []
    while current is not None and current not in chain and len(chain) < HISTORY_MAX:
        chain.append(current)
        current = renders.get(_source_of(current))
    entries = []
    for render in reversed(chain):
        entry: dict = {"imagen": _label(render)}
        if render is chain[0]:
            entry["es_la_imagen_de_partida"] = True
        if render.inpaint is not None:
            entry["retoque_pedido_por_el_usuario"] = render.inpaint.instruction
        if render.prompt_info is not None:
            entry["lo_que_se_entendio"] = render.prompt_info.interpretation
        if render is chain[0]:
            entry["prompt"] = render.prompt
        entries.append(entry)
    return entries


def previous_section(
    project: ProjectMetadata, stage: RenderStage, inputs: list[InputRole]
) -> list[dict]:
    """Generaciones anteriores de la etapa (B-094): la seleccionada y la más reciente, con su
    prompt, lo que se entendió y sus dudas, para dar continuidad y resolverlas. Sin las que ya
    son entradas de esta generación (la imagen de partida va en el historial)."""
    used = {item.asset.id for item in inputs}
    own = [r for r in project.renders
           if r.stage is stage and r.prompt_info is not None and r.id not in used]  # fmt: skip
    chosen = [r for r in own if r.status is RenderStatus.SELECTED]
    latest = max(own, key=lambda r: r.created_at, default=None)
    if latest is not None and latest not in chosen:
        chosen.append(latest)
    return [
        {
            "imagen": _label(r),
            "seleccionada": r.status is RenderStatus.SELECTED,
            "prompt": r.prompt,
            "lo_que_se_entendio": r.prompt_info.interpretation,
            "dudas": r.prompt_info.open_questions,
        }
        for r in chosen
        if r.prompt_info is not None
    ]


def build_context(
    project: ProjectMetadata,
    inputs: list[InputRole],
    references: list[Asset],
    indications: str,
    size: str,
    extras: dict[str, str] | None = None,
    stage: RenderStage | None = None,
) -> str:
    numbers = {item.asset.id: i for i, item in enumerate(inputs, start=1)}
    images = "\n".join(
        f"- Imagen {i}: {item.role} — «{item.asset.original_name}»"
        for i, item in enumerate(inputs, start=1)
    )
    sections = [
        "## Proyecto",
        f"Nombre: {project.name}",
        "## Descripción del proyecto (escrita por el usuario)",
        project.description.strip() or "(sin descripción)",
        "## Imágenes que recibirá el modelo de imagen (en este orden)",
        images or "(ninguna)",
        "## Lo marcado en las fichas de las referencias activas (y lo que hay que ignorar)",
        json.dumps(references_section(references, numbers), ensure_ascii=False, indent=2)
        if references
        else "(ninguna)",
        "## Indicaciones del usuario para esta generación",
        indications.strip() or "(ninguna)",
        "## Formato de salida",
        f"{size} px",
    ]
    if history := history_section(project, inputs):
        sections += [
            "## Historial de la imagen de partida (de la más antigua a ella)",
            json.dumps(history, ensure_ascii=False, indent=2),
        ]
    if stage is not None and (previous := previous_section(project, stage, inputs)):
        sections += [
            "## Generaciones anteriores de esta etapa (continuidad y dudas pendientes)",
            json.dumps(previous, ensure_ascii=False, indent=2),
        ]
    for title, text in (extras or {}).items():  # p. ej. auditoría o modo retoque
        sections += [f"## {title}", text]
    return "\n\n".join(sections)


def system_prompt(stage: RenderStage) -> tuple[str, str]:
    """Texto y versión del prompt de sistema: el de la etapa más los criterios comunes."""
    own, criteria = load_prompt(PROMPT_FILES[stage]), load_prompt(CRITERIA_FILE)
    return f"{own.text}\n\n{criteria.text}", f"{own.version}+{criteria.version}"


async def write_prompt(
    repo: ProjectRepository,
    client: FoundryClient,
    project: ProjectMetadata,
    stage: RenderStage,
    inputs: list[InputRole],
    references: list[Asset],
    indications: str,
    size: str,
    extras: dict[str, str] | None = None,
) -> WrittenPrompt:
    """El PROMPT_ARCHITECT escribe el prompt de la generación (ve también las imágenes)."""
    instructions, version = system_prompt(stage)
    images: list[InputImage] = [
        (
            await prepare_image(
                await repo.read_asset_bytes(project.id, item.asset.id), WRITER_MAX_SIDE_PX
            )
        ).model_copy(update={"detail": WRITER_IMAGE_DETAIL})
        for item in inputs
    ]
    result = await client.complete_text(
        Role.PROMPT_ARCHITECT,
        TextRequest(
            instructions=instructions,
            input=build_context(project, inputs, references, indications, size, extras, stage),
            images=images,
            json_schema=SCHEMA,
            schema_name="prompt_generacion",
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
    )
    try:
        prompt = StagePrompt.model_validate(result.data)
    except ValidationError as exc:
        raise PipelineError("El prompt devuelto por el modelo no cumple el esquema") from exc
    return WrittenPrompt(prompt=prompt, version=version)
