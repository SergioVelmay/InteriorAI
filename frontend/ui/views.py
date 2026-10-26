"""Funciones puras de presentación (sin Gradio): testeables sin navegador."""

from __future__ import annotations

import html
import json
from collections import Counter
from typing import Any, Literal

from shared.models import (
    RECIPE_GROUPS,
    Asset,
    AssetKind,
    ProjectMetadata,
    ProjectSummary,
    ProjectUpdate,
    RecipeElement,
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
        # Orden (B-050): proyecto, backend y modo; los avisos de gasto, al final.
        f'<div class="iai-badges">{project}{status}{mode}{spending}</div>'
        "</div>"
    )


def gallery_caption(project: ProjectMetadata) -> str:
    return f"{project.name} · {project.updated_at:%d/%m/%Y}"


def project_summary_md(project: ProjectMetadata, costs: dict[str, Any] | None) -> str:
    """Resumen del proyecto (B-060): referencias, activas y una línea por etapa."""
    references = [a for a in project.assets if a.kind is AssetKind.REFERENCIA]
    active = sum(1 for a in references if a.sheet is not None and a.sheet.active)
    stages = Counter(r.stage for r in project.renders)
    selected_final = any(
        r.stage is RenderStage.FINAL and r.status is RenderStatus.SELECTED for r in project.renders
    )
    lines = [
        f"### {html.escape(project.name)}",
        f"Actualizado el {project.updated_at:%d/%m/%Y %H:%M} UTC",
        "",
        f"- Imágenes de referencia: **{len(references)}**",
        f"- Referencias activas: **{active} de {len(references)}**",
        f"- Bocetos generados: **{stages[RenderStage.DRAFT]}**",
        f"- Composiciones generadas: **{stages[RenderStage.COMPOSITION]}**",
        f"- Renders finales generados: **{stages[RenderStage.FINAL]}**",
        f"- Render final elegido: **{'SÍ' if selected_final else 'NO'}**",
    ]
    if costs is not None:
        totals = costs.get("totals", {})
        lines.append(
            f"- Gasto real estimado en IA: **{totals.get('cost_eur', 0):.4f} €** en "
            f"{totals.get('calls', 0)} llamadas"
        )
        # Desglose por rol (B-027), del más caro al más barato.
        for group in sorted(costs.get("by_role", []), key=lambda g: -g["cost_eur"]):
            lines.append(
                f"  - {group['key']}: {group['cost_eur']:.4f} € · {group['calls']} llamada(s)"
            )
    return "\n".join(lines)


def calls_label(costs: dict[str, Any] | None) -> str:
    """Título del desplegable con las llamadas del proyecto (B-027)."""
    if not costs:
        return "Llamadas de IA"
    shown, total = len(costs.get("records", [])), costs.get("totals", {}).get("calls", 0)
    suffix = f" (las {shown} últimas de {total})" if shown < total else f" ({total})"
    return f"Llamadas de IA{suffix}"


def form_values(project: ProjectMetadata) -> list[Any]:
    """Valores del formulario de edición, en el orden de `FORM_FIELDS`."""
    return [project.name, project.description]


FORM_FIELDS = ("name", "description")


def parse_form(values: list[Any]) -> ProjectUpdate:
    """Formulario → `ProjectUpdate`. Lanza `ValueError` con un mensaje en español."""
    data = dict(zip(FORM_FIELDS, values, strict=True))
    if not (data["name"] or "").strip():
        raise ValueError("El nombre no puede estar vacío")
    return ProjectUpdate(name=data["name"], description=data["description"] or "")


# --- Referencias: receta y ficha (Paso 21, B-029 y B-030) --------------------------------

SOURCE_LABELS = {
    "nota_usuario": "de las notas",
    "cota_imagen": "cota en la imagen",
    "estimada": "estimada",
}
# Coste orientativo del análisis de una imagen (Paso 21: con sol, 0,017-0,044 €).
COST_ANALYSIS = 0.04


def sheet_status(asset: Asset) -> str:
    sheet = asset.sheet
    if sheet is None:
        return "Sin analizar"
    if not sheet.active:
        return "Descartada"
    return f"Activa · {len(sheet.selected)} marcado(s)"


def asset_caption(asset: Asset) -> str:
    """Pie de una referencia (B-065): el nombre arriba y, debajo, tamaño y estado."""
    details = []
    if asset.width_px and asset.height_px:
        details.append(f"{asset.width_px}x{asset.height_px}")
    if asset.kind is AssetKind.REFERENCIA:
        details.append(sheet_status(asset))
    return f"{asset.original_name}\n{' · '.join(details)}" if details else asset.original_name


def asset_info_md(asset: Asset) -> str:
    size = (
        f"{asset.size_bytes / 1_048_576:.2f} MB"
        if asset.size_bytes >= 1_048_576
        else (f"{asset.size_bytes / 1024:.0f} KB")
    )
    dims = f" · {asset.width_px}x{asset.height_px} px" if asset.width_px else ""
    lines = [
        f"**{html.escape(asset.original_name)}**  ",
        f"{size}{dims} · subida el {asset.created_at:%d/%m/%Y %H:%M} UTC · "
        f"ficha: **{sheet_status(asset)}**",
    ]
    if asset.sheet is not None:
        lines.append(f"\n{html.escape(asset.sheet.recipe.summary)}")
    return "\n".join(lines)


def _number(value: float | None) -> str:
    return "?" if value is None else f"{value:g}".replace(".", ",")


def element_label(element: RecipeElement) -> str:
    """Texto completo de un elemento: nombre, detalle y medidas con su origen (las estimadas,
    marcadas). En la ficha es el tooltip de la casilla (Paso 23)."""
    text = element.label + (f" — {element.detail}" if element.detail else "")
    if element.dimensions_source != "ninguna":
        d = element.dimensions_cm
        values = [d.width_cm, d.depth_cm, d.height_cm]
        if any(v is not None for v in values):
            measures = " x ".join(_number(v) for v in values)
            text += f" ({measures} cm, {SOURCE_LABELS[element.dimensions_source]})"
    return text


def sheet_groups(asset: Asset | None) -> dict[str, tuple[list[tuple[str, str]], list[str]]]:
    """Por grupo de la receta: (casillas [(nombre, id)], ids marcados). Vacío si no hay ficha.

    Paso 23: la casilla muestra solo el nombre; el detalle va en el tooltip (`sheet_tooltips`).
    """
    groups: dict[str, tuple[list[tuple[str, str]], list[str]]] = {
        group: ([], []) for group in RECIPE_GROUPS
    }
    if asset is None or asset.sheet is None:
        return groups
    selected = set(asset.sheet.selected)
    for element_id, element in asset.sheet.recipe.elements():
        choices, marked = groups[element_id.split(":")[0]]
        choices.append((element.label, element_id))
        if element_id in selected:
            marked.append(element_id)
    return groups


def sheet_tooltips(asset: Asset | None) -> dict[str, list[str]]:
    """Por grupo, el texto completo de cada casilla en su orden (tooltip al pasar el ratón)."""
    tips: dict[str, list[str]] = {}
    if asset is None or asset.sheet is None:
        return tips
    for element_id, element in asset.sheet.recipe.elements():
        tips.setdefault(element_id.split(":")[0], []).append(element_label(element))
    return tips


def tooltips_html(tips: dict[str, list[str]]) -> str:
    """Contenedor oculto con los tooltips de la ficha: `theme.FORCE_DARK_JS` los aplica como
    `title` de cada casilla cuando cambia la página."""
    data = html.escape(json.dumps(tips, ensure_ascii=False), quote=True)
    return f'<div data-tips="{data}"></div>'


def selected_ids(values: list[list[str] | None]) -> list[str]:
    """Lo marcado en las casillas de todos los grupos (en el orden de `RECIPE_GROUPS`)."""
    return [element_id for group in values for element_id in (group or [])]
