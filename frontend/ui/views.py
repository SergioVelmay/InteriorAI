"""Funciones puras de presentación (sin Gradio): testeables sin navegador."""

from __future__ import annotations

import html
from collections import Counter
from typing import Any, Literal

from shared.models import (
    Asset,
    AssetKind,
    Dimensions,
    DimensionsCm,
    ProjectMetadata,
    ProjectSummary,
    ProjectUpdate,
    ReferenceAnalysis,
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


def header_html(
    health: Health | None,
    active: ProjectSummary | ProjectMetadata | None,
    alerts: dict[str, Any] | None = None,
) -> str:
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
    spending = ""  # avisos de gasto real (B-021): solo informan
    if alerts:
        current = next(
            (p for p in alerts["projects"] if active and p["project_id"] == str(active.id)), None
        )
        if current and current["exceeded"]:
            spending += badge("warn", f"Gasto del proyecto: {current['cost_eur']:.2f} €")
        if alerts["total"]["exceeded"]:
            spending += badge("warn", f"Gasto total: {alerts['total']['cost_eur']:.2f} €")
    return (
        '<div class="iai-header">'
        '<div class="iai-brand"><h1>InteriorAI</h1>'
        "<p>Estudio de interiorismo asistido por IA · supervisión humana en cada etapa</p></div>"
        f'<div class="iai-badges">{status}{mode}{project}{spending}</div>'
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


# --- Assets (Paso 12) ---------------------------------------------------------------------

ANALYSIS_LABELS = {None: "Sin indexar", "proposed": "Propuesta (IA)", "validated": "Validada ✓"}
CATEGORY_CHOICES = [
    ("Sofá", "sofa"), ("Mesa", "mesa"), ("Silla", "silla"), ("Cama", "cama"),
    ("Almacenaje", "almacenaje"), ("Lámpara", "lampara"), ("Alfombra", "alfombra"),
    ("Textil", "textil"), ("Decoración", "decoracion"), ("Revestimiento", "revestimiento"),
    ("Ambiente (inspiración)", "ambiente"), ("Otro", "otro"),
]  # fmt: skip
DIMENSION_SOURCE_CHOICES = [
    ("Nota del usuario", "nota_usuario"),
    ("Leída en la imagen", "imagen"),
    ("Desconocido", "desconocido"),
]


def analysis_status(asset: Asset) -> str:
    return ANALYSIS_LABELS[asset.analysis.status if asset.analysis else None]


def asset_caption(asset: Asset) -> str:
    parts = [asset.original_name]
    if asset.width_px and asset.height_px:
        parts.append(f"{asset.width_px}x{asset.height_px}")
    if asset.kind is AssetKind.REFERENCIA:
        parts.append(analysis_status(asset))
    return " · ".join(parts)


def asset_info_md(asset: Asset) -> str:
    size = (
        f"{asset.size_bytes / 1_048_576:.2f} MB"
        if asset.size_bytes >= 1_048_576
        else (f"{asset.size_bytes / 1024:.0f} KB")
    )
    dims = f" · {asset.width_px}x{asset.height_px} px" if asset.width_px else ""
    status = f" · ficha: **{analysis_status(asset)}**" if asset.kind is AssetKind.REFERENCIA else ""
    return (
        f"**{html.escape(asset.original_name)}**  \n"
        f"{asset.kind.label} · {size}{dims} · "
        f"subido el {asset.created_at:%d/%m/%Y %H:%M} UTC{status}"
    )


def _join(values: list[str]) -> str:
    return ", ".join(values)


def _split(text: str | None) -> list[str]:
    seen: list[str] = []
    for part in (text or "").split(","):
        part = part.strip()
        if part and part not in seen:
            seen.append(part)
    return seen


ANALYSIS_FIELDS = (
    "category", "item_name", "brand", "product_name", "style_tags", "colors", "materials",
    "width_cm", "depth_cm", "height_cm", "dimensions_source", "summary", "design_relevance",
)  # fmt: skip


def analysis_form_values(asset: Asset) -> list[Any]:
    """Ficha → valores del formulario (en el orden de `ANALYSIS_FIELDS`); vacío si no hay."""
    if asset.analysis is None:
        return ["otro", "", "", "", "", "", "", None, None, None, "desconocido", "", ""]
    r = asset.analysis.result
    d = r.dimensions_cm
    return [
        r.category.value, r.item_name, r.brand or "", r.product_name or "", _join(r.style_tags),
        _join(r.colors), _join(r.materials), d.width_cm, d.depth_cm, d.height_cm,
        r.dimensions_source, r.summary, r.design_relevance,
    ]  # fmt: skip


def parse_analysis_form(values: list[Any]) -> ReferenceAnalysis:
    """Formulario → `ReferenceAnalysis`. Lanza `ValueError` con mensaje en español."""
    data = dict(zip(ANALYSIS_FIELDS, values, strict=True))
    if not (data["item_name"] or "").strip():
        raise ValueError("La ficha necesita un nombre de objeto")
    dims = {k: data.pop(k) for k in ("width_cm", "depth_cm", "height_cm")}
    if any(v is not None and v < 0 for v in dims.values()):
        raise ValueError("Las medidas no pueden ser negativas")
    known = any(v is not None for v in dims.values())
    if known and data["dimensions_source"] == "desconocido":
        raise ValueError("Indica de dónde salen las medidas (nota del usuario o imagen)")
    return ReferenceAnalysis(
        category=data["category"],
        item_name=data["item_name"],
        brand=(data["brand"] or "").strip() or None,
        product_name=(data["product_name"] or "").strip() or None,
        style_tags=_split(data["style_tags"]),
        colors=_split(data["colors"]),
        materials=_split(data["materials"]),
        dimensions_cm=DimensionsCm(**dims),
        dimensions_source=data["dimensions_source"] if known else "desconocido",
        summary=data["summary"] or "",
        design_relevance=data["design_relevance"] or "",
    )
