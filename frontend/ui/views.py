"""Funciones puras de presentación (sin Gradio): testeables sin navegador."""

from __future__ import annotations

import html
from collections import Counter
from typing import Any, Literal

from shared.models import (
    AssetKind,
    Dimensions,
    ProjectMetadata,
    ProjectSummary,
    ProjectUpdate,
    RenderStage,
    RenderStatus,
)
from ui.api_client import Health

BadgeLevel = Literal["ok", "warn", "error", "pending", "neutral"]


def badge(level: BadgeLevel, text: str) -> str:
    return (
        f'<span class="iai-badge iai-{level}"><span class="iai-dot"></span>'
        f"{html.escape(text)}</span>"
    )


def header_html(health: Health | None, active: ProjectSummary | ProjectMetadata | None) -> str:
    if health is None:
        status = badge("error", "Backend no disponible")
        mode = ""
    else:
        ok = health.status == "ok"
        status = badge("ok" if ok else "warn", "Backend conectado" if ok else "Backend degradado")
        mode = (
            badge("neutral", "Simulación · sin coste")
            if health.mode == "mock"
            else badge("warn", "Azure · con coste")
        )
    project = (
        badge("ok", f"Proyecto: {active.name}")
        if active
        else badge("pending", "Sin proyecto activo")
    )
    return (
        '<div class="iai-header">'
        '<div class="iai-brand"><h1>InteriorAI</h1>'
        "<p>Estudio de interiorismo asistido por IA · supervisión humana en cada etapa</p></div>"
        f'<div class="iai-badges">{status}{mode}{project}</div>'
        "</div>"
    )


def gallery_caption(project: ProjectMetadata) -> str:
    parts = [project.name]
    if project.space_type.label.casefold() != project.name.strip().casefold():
        parts.append(project.space_type.label)  # sin repetir si el nombre ya es el tipo
    return " · ".join([*parts, f"{project.updated_at:%d/%m/%Y}"])


def project_summary_md(project: ProjectMetadata, costs: dict[str, Any] | None) -> str:
    kinds = Counter(a.kind for a in project.assets)
    stages = Counter(r.stage for r in project.renders)
    selected_final = any(
        r.stage is RenderStage.FINAL and r.status is RenderStatus.SELECTED for r in project.renders
    )
    latest_brief = max(project.briefs, key=lambda b: b.version, default=None)
    brief = f"v{latest_brief.version} · {latest_brief.status}" if latest_brief else "sin brief"
    lines = [
        f"### {html.escape(project.name)}",
        f"**{project.space_type.label}** · actualizado el {project.updated_at:%d/%m/%Y %H:%M} UTC",
        "",
        f"- Capturas de SketchUp: **{kinds[AssetKind.CAPTURA_SKETCHUP]}** · "
        f"planos: **{kinds[AssetKind.PLANO]}** · referencias: **{kinds[AssetKind.REFERENCIA]}**",
        f"- Brief: **{brief}**",
        f"- Bocetos: **{stages[RenderStage.DRAFT]}** · composiciones: "
        f"**{stages[RenderStage.COMPOSITION]}** · renders finales: **{stages[RenderStage.FINAL]}**",
        f"- Render final elegido: **{'sí' if selected_final else 'no'}**",
    ]
    if costs is not None:
        totals = costs.get("totals", {})
        simulated = " (incluye simulaciones)" if costs.get("includes_simulated") else ""
        lines.append(
            f"- Coste estimado de IA: **{totals.get('cost_eur', 0):.4f} €** en "
            f"{totals.get('calls', 0)} llamadas{simulated}"
        )
    return "\n".join(lines)


def form_values(project: ProjectMetadata) -> list[Any]:
    """Valores del formulario de edición, en el orden de `FORM_FIELDS`."""
    d = project.dimensions
    return [
        project.name,
        project.space_type.value,
        project.description,
        project.design_notes,
        d.width_m if d else None,
        d.length_m if d else None,
        d.height_m if d else None,
        project.style,
        project.budget_eur,
    ]


FORM_FIELDS = (
    "name", "space_type", "description", "design_notes", "width_m", "length_m", "height_m",
    "style", "budget_eur",
)  # fmt: skip


def parse_form(values: list[Any]) -> ProjectUpdate:
    """Formulario → `ProjectUpdate`. Lanza `ValueError` con un mensaje en español."""
    data = dict(zip(FORM_FIELDS, values, strict=True))
    width, length, height = data.pop("width_m"), data.pop("length_m"), data.pop("height_m")
    if (width is None) != (length is None):
        raise ValueError("Indica ancho y largo juntos, o deja ambos vacíos")
    dimensions = (
        Dimensions(width_m=width, length_m=length, height_m=height or None)
        if width is not None
        else None
    )
    if not (data["name"] or "").strip():
        raise ValueError("El nombre no puede estar vacío")
    return ProjectUpdate(
        name=data["name"],
        space_type=data["space_type"],
        description=data["description"] or "",
        design_notes=data["design_notes"] or "",
        dimensions=dimensions,
        style=data["style"] or "",
        budget_eur=data["budget_eur"],
    )
