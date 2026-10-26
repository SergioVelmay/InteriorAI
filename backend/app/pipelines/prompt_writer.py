"""Prompt automático de cada generación (Paso 22: sustituye al brief de la v1).

Al pulsar «Generar» en cualquier etapa, el PROMPT_ARCHITECT escribe el prompt de ESA generación
con sus entradas reales: la descripción del proyecto, las imágenes que recibirá el modelo de
imagen (con su papel), lo marcado en las fichas de las referencias activas y las indicaciones
del usuario. Devuelve también lo que ha entendido y sus dudas, que se guardan con cada imagen.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

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
    RenderStage,
    StagePrompt,
)
from shared.roles import Role

SCHEMA = strict_schema(StagePrompt)
MAX_OUTPUT_TOKENS = 6_000  # incluye el razonamiento del despliegue
WRITER_MAX_SIDE_PX = 1_024  # el escritor ve las imágenes para describirlas, no para copiarlas
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


def build_context(
    project: ProjectMetadata,
    inputs: list[InputRole],
    references: list[Asset],
    indications: str,
    size: str,
    extras: dict[str, str] | None = None,
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
    for title, text in (extras or {}).items():  # p. ej. auditoría o modo retoque
        sections += [f"## {title}", text]
    return "\n\n".join(sections)


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
    system = load_prompt(PROMPT_FILES[stage])
    images: list[InputImage] = [
        await prepare_image(
            await repo.read_asset_bytes(project.id, item.asset.id), WRITER_MAX_SIDE_PX
        )
        for item in inputs
    ]
    result = await client.complete_text(
        Role.PROMPT_ARCHITECT,
        TextRequest(
            instructions=system.text,
            input=build_context(project, inputs, references, indications, size, extras),
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
    return WrittenPrompt(prompt=prompt, version=system.version)
