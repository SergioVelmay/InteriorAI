"""Presentación pura de la pestaña Estudio (sin Gradio): imágenes, costes, auditoría y retoques.

Desde el Paso 22 el Estudio tiene tres pestañas (Bocetos, Composición y Render Final) y no hay
brief: cada generación guarda su prompt automático (`RenderRecord.prompt_info`).
"""

from __future__ import annotations

import html
import io
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

from shared.models import (
    RECIPE_GROUPS,
    Asset,
    AssetKind,
    ProjectMetadata,
    RenderAudit,
    RenderRecord,
    RenderStage,
    RenderStatus,
)

# Coste estimado por acción (EUR, límite alto de lo observado en las pruebas reales).
COST_PER_IMAGE = {
    RenderStage.DRAFT: 0.015,
    RenderStage.COMPOSITION: 0.035,
    RenderStage.FINAL: 0.095,
}
# Bocetos (Paso 22, medido con 3 imágenes de entrada en calidad media: 4 bocetos = 0,142 € y
# 5 = 0,177 €): cada imagen de entrada ≈ 0,042 € (tokens de imagen, lo que más pesa) y cada
# boceto según su calidad, más el prompt.
COST_DRAFT_INPUT = 0.042
COST_DRAFT_OUTPUT = {"low": 0.003, "medium": 0.009, "high": 0.035}
COST_PROMPT = 0.002  # el PROMPT_ENGINEER escribe el prompt de cada generación (luna)
MAX_DRAFT_INPUTS = 7  # imagen base + 6 apoyos
# Retoque: solo la composición, con máscara nativa (B-038).
COST_INPAINT = {RenderStage.COMPOSITION: 0.035}
INPAINT_STAGES = frozenset(COST_INPAINT)
COST_AUDIT = 0.25
CONFIRM_THRESHOLD_EUR = 0.15  # en modo azure, por encima se pide un segundo clic (B-043)

STATUS_ICONS = {RenderStatus.GENERATED: "○", RenderStatus.SELECTED: "●"}
CHECK_ICONS = {"ok": "✅", "aviso": "⚠️", "fallo": "❌"}
VERDICTS = {
    "conforme": "✅ Conforme",
    "conforme_con_observaciones": "⚠️ Conforme con observaciones",
    "no_conforme": "❌ No conforme",
}
DRAFT_SIZES = [  # formato de los bocetos: tamaño con su proporción (B-040)
    ("1536 x 1024 (3:2)", "1536x1024"),
    ("1024 x 1024 (1:1)", "1024x1024"),
    ("1024 x 1536 (2:3)", "1024x1536"),
]
QUALITIES = [("Baja", "low"), ("Media", "medium"), ("Alta", "high")]


def euros(value: float | None) -> str:
    return "sin precio" if value is None else f"{value:.4f} €"


def needs_confirmation(mode: str | None, estimated_eur: float) -> bool:
    return mode == "azure" and estimated_eur > CONFIRM_THRESHOLD_EUR


def cost_hint(estimated_eur: float, mode: str | None) -> str:
    if mode != "azure":
        return "Simulación: sin coste"
    return f"Azure: ≈ {estimated_eur:.3f} €"


def inpaint_hint(stage: RenderStage | None, mode: str | None) -> str | None:
    """Coste del retoque de una imagen de esta etapa, o None si la etapa no admite retoques."""
    if stage not in INPAINT_STAGES:
        return None
    return cost_hint(COST_INPAINT[stage], mode)


def draft_cost(n: int, quality: str, inputs: int) -> float:
    """Coste estimado de un lote de bocetos con `inputs` imágenes de entrada."""
    inputs = min(inputs, MAX_DRAFT_INPUTS)
    return COST_PROMPT + inputs * COST_DRAFT_INPUT + n * COST_DRAFT_OUTPUT.get(quality, 0.009)


def _dims(d: Any) -> str:
    """Ancho x fondo x alto en cm; `?` lo desconocido (nunca se inventa)."""
    return " x ".join("?" if v is None else f"{v:g}" for v in (d.width_cm, d.depth_cm, d.height_cm))


# --- Referencias activas (Bocetos) -------------------------------------------------------------


def active_references(project: ProjectMetadata) -> list[Asset]:
    return sorted(
        (
            a
            for a in project.assets
            if a.kind is AssetKind.REFERENCIA and a.sheet is not None and a.sheet.active
        ),
        key=lambda a: a.created_at,
    )


def reference_summary(asset: Asset) -> str:
    """Pie de una referencia activa: lo que se usa de ella (grupos marcados)."""
    groups = asset.sheet.selected_elements() if asset.sheet else {}
    used = ", ".join(f"{RECIPE_GROUPS[g].split(' (')[0].lower()} ({len(e)})"
                     for g, e in groups.items())  # fmt: skip
    return f"{asset.original_name} · {used}"


def draft_inputs(project: ProjectMetadata) -> int:
    """Imágenes que recibiría el modelo de bocetos: las referencias activas (máx. 7)."""
    return min(len(active_references(project)), MAX_DRAFT_INPUTS)


# --- Renders ---------------------------------------------------------------------------------


def renders_of(project: ProjectMetadata, stage: RenderStage) -> list[RenderRecord]:
    return sorted(
        (r for r in project.renders if r.stage is stage), key=lambda r: r.created_at, reverse=True
    )


def render_caption(render: RenderRecord) -> str:
    audit = ""
    if render.audits:
        audit = f" · auditoría {render.audits[-1].report.score}/100"
    retouch = " · retoque" if render.inpaint else " · bruto" if render.raw_of_render_id else ""
    return (
        f"{STATUS_ICONS[render.status]} {render.status}{retouch}{audit} · {euros(render.cost_eur)}"
    )


def selected_choices(project: ProjectMetadata, stage: RenderStage) -> list[tuple[str, str]]:
    return [
        (f"{r.stage.label} {r.id.hex[:8]} · {r.created_at:%d/%m %H:%M}", str(r.id))
        for r in renders_of(project, stage)
        if r.status is RenderStatus.SELECTED
    ]


def reference_choices(project: ProjectMetadata) -> list[tuple[str, str]]:
    """Referencias para el render final: las activas (ficha con algo marcado, B-030)."""
    return [
        (a.original_name, str(a.id))
        for a in project.assets
        if a.kind is AssetKind.REFERENCIA and a.sheet is not None and a.sheet.active
    ]


def default_textures(project: ProjectMetadata) -> list[str]:
    """Texturas marcadas por defecto en el render final: las referencias activas que no aportan
    la perspectiva (la vista ya está en la composición)."""
    return [
        str(a.id)
        for a in active_references(project)
        if not any(e.startswith("perspectiva:") for e in a.sheet.selected)  # type: ignore[union-attr]
    ]


def selected_render(project: ProjectMetadata, stage: RenderStage) -> RenderRecord | None:
    """La imagen seleccionada de una etapa (una como mucho, B-043)."""
    return next((r for r in renders_of(project, stage) if r.status is RenderStatus.SELECTED), None)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {html.escape(i)}" for i in items)


def render_title_md(render: RenderRecord | None) -> str:
    """Línea bajo la imagen grande: etapa, estado, tamaño y coste."""
    if render is None:
        return "_Genera o elige una imagen para verla aquí._"
    state = "seleccionado" if render.status is RenderStatus.SELECTED else "sin seleccionar"
    return (
        f"**{render.stage.label} `{render.id.hex[:8]}`** · {STATUS_ICONS[render.status]} {state}"
        f" · {render.size} · calidad {render.quality or '—'} · {euros(render.cost_eur)} · "
        f"{render.created_at:%d/%m/%Y %H:%M} UTC"
    )


def render_detail_md(project: ProjectMetadata, render: RenderRecord | None) -> str:
    """«Ver más» (B-036, B-047): lo que entendió el PROMPT_ENGINEER, el prompt enviado y el
    resto de la trazabilidad. Las imágenes de la v1 muestran su brief en lugar del prompt
    automático."""
    if render is None:
        return ""
    names = {a.id: a.original_name for a in project.assets}
    labels = {r.id: f"{r.stage.label} {r.id.hex[:8]}" for r in project.renders}
    inputs = ", ".join(labels.get(i) or names.get(i, str(i)[:8]) for i in render.input_asset_ids)
    lines = []
    info = render.prompt_info
    if info is not None:
        lines.append(f"**Lo que ha entendido la IA:** {html.escape(info.interpretation)}")
        if info.open_questions:
            lines += ["**Dudas** (acláralas en las indicaciones de la próxima generación)",
                      _bullets(info.open_questions)]  # fmt: skip
    elif render.brief_version is not None:
        lines.append(f"Imagen de la v1, generada con el brief v{render.brief_version}.")
    lines.append(f"**Entradas:** {html.escape(inputs)} · {render.deployment}")
    if render.inpaint:
        info_inpaint = render.inpaint
        method = "máscara" if info_inpaint.method == "mascara" else "imagen regenerada y recortada"
        lines.append(
            f"**Retoque de** `{info_inpaint.source_render_id.hex[:8]}`: "
            f"«{html.escape(info_inpaint.instruction)}» · zona {info_inpaint.coverage:.0%} · "
            f"{method}"
        )
    if render.raw_of_render_id:
        lines.append(
            f"**Salida en bruto del retoque** `{render.raw_of_render_id.hex[:8]}` (v1): la "
            "imagen completa que generó el modelo, sin recomponer"
        )
    if render.previous_attempt_id:
        lines.append(
            f"**Sustituye a:** `{render.previous_attempt_id.hex[:8]}` (rechazado en la v1)"
        )
    if render.feedback:
        lines.append(f"**Tus comentarios al rechazarla (v1):** {html.escape(render.feedback)}")
    lines.append(f"**Prompt enviado al modelo de imagen**\n\n```\n{render.prompt}\n```")
    return "\n\n".join(lines)


def render_inputs(
    project: ProjectMetadata, render: RenderRecord | None, data_dir: Path
) -> list[tuple[str, str]]:
    """Miniaturas de todo lo enviado al modelo (B-047): imágenes de entrada y máscara."""
    if render is None:
        return []
    assets = {a.id: a for a in project.assets}
    labels = {r.id: f"{r.stage.label} {r.id.hex[:8]}" for r in project.renders}
    items = []
    for i, asset_id in enumerate(render.input_asset_ids, start=1):
        asset = assets.get(asset_id)
        if asset is None:
            continue
        path = data_dir / str(project.id) / asset.kind.folder / asset.stored_name
        items.append((str(path), f"{i}. {labels.get(asset_id) or asset.original_name}"))
    if render.inpaint is not None:
        mask = data_dir / str(project.id) / AssetKind.RENDER.folder / render.inpaint.mask_file
        items.append((str(mask), "Máscara (blanco = zona retocada)"))
    return items


def audit_markdown(audit: RenderAudit | None) -> str:
    if audit is None:
        return "_Sin auditoría. Es opcional: compara la imagen con tu imagen base._"
    r = audit.report
    checks = "\n".join(
        f"| {c.aspect.replace('_', ' ')} | {CHECK_ICONS[c.status]} | {html.escape(c.finding)} |"
        for c in r.checks
    )
    deviations = "\n".join(
        f"| {html.escape(d.element)} | {d.severity} | {html.escape(d.expected)} | "
        f"{html.escape(d.observed)} |"
        for d in r.deviations
    )
    parts = [
        f"#### Auditoría: {VERDICTS[r.verdict]} · {r.score}/100",
        f"{audit.reasoning_effort} · {euros(audit.cost_eur)} · {audit.created_at:%d/%m %H:%M} UTC",
        html.escape(r.summary),
        "| Aspecto | | Hallazgo |\n|---|---|---|\n" + checks,
    ]
    if deviations:
        parts.append(
            "**Desviaciones**\n\n"
            "| Elemento | Severidad | Esperado | Observado |\n|---|---|---|---|\n" + deviations
        )
    if r.suggested_prompt_adjustments.strip():
        parts.append(
            "<details><summary>Correcciones propuestas (añádelas a tus indicaciones)</summary>"
            "\n\n"
            f"```\n{r.suggested_prompt_adjustments}\n```\n</details>"
        )
    return "\n\n".join(parts)


# --- Retoque ---------------------------------------------------------------------------------


def editor_mask(value: dict[str, Any] | None) -> bytes | None:
    """Capas pintadas del editor → PNG RGBA (opaco = zona a editar), o None si no hay trazos."""
    layers = [layer for layer in (value or {}).get("layers") or [] if layer is not None]
    if not layers:
        return None
    size = layers[0].size
    alpha = Image.new("L", size, 0)
    for layer in layers:
        channel = layer.convert("RGBA").getchannel("A")
        alpha = ImageChops.lighter(alpha, channel if channel.size == size else channel.resize(size))
    alpha = alpha.point(lambda v: 255 if v else 0)
    if alpha.getbbox() is None:
        return None
    mask = Image.new("RGBA", size, (255, 255, 255, 0))
    mask.putalpha(alpha)
    buffer = io.BytesIO()
    mask.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()
