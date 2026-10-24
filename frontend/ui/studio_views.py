"""Presentación pura de la pestaña Estudio (sin Gradio): brief, renders, auditoría y costes."""

from __future__ import annotations

import html
import io
from typing import Any

from PIL import Image, ImageChops

from shared.models import (
    AssetKind,
    BriefStatus,
    DesignBrief,
    DimensionsCm,
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
# Retoque: solo la composición, con máscara nativa (B-038).
COST_INPAINT = {RenderStage.COMPOSITION: 0.035}
INPAINT_STAGES = frozenset(COST_INPAINT)
COST_BRIEF = 0.05
COST_AUDIT = 0.25
CONFIRM_THRESHOLD_EUR = 0.05  # en modo azure, por encima se pide un segundo clic

STATUS_ICONS = {RenderStatus.GENERATED: "○", RenderStatus.SELECTED: "●"}
CHECK_ICONS = {"ok": "✅", "aviso": "⚠️", "fallo": "❌"}
VERDICTS = {
    "conforme": "✅ Conforme",
    "conforme_con_observaciones": "⚠️ Conforme con observaciones",
    "no_conforme": "❌ No conforme",
}


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


# --- Brief ----------------------------------------------------------------------------------


def latest_brief(project: ProjectMetadata) -> DesignBrief | None:
    return max(project.briefs, key=lambda b: b.version, default=None)


def approved_brief(project: ProjectMetadata) -> DesignBrief | None:
    return next((b for b in project.briefs if b.status is BriefStatus.APPROVED), None)


def brief_choices(project: ProjectMetadata) -> list[tuple[str, str]]:
    return [
        (f"v{b.version} · {b.status}{' · editado' if b.edited_by_user else ''}", str(b.id))
        for b in sorted(project.briefs, key=lambda b: b.version, reverse=True)
    ]


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {html.escape(i)}" for i in items) or "_(ninguno)_"


def brief_markdown(brief: DesignBrief | None) -> str:
    if brief is None:
        return "_Aún no hay brief. Genera el primero con tus notas, capturas y referencias._"
    c = brief.content
    furniture = "\n".join(
        f"| {html.escape(f.name)} | {_dims(f.dimensions_cm)} | "
        f"{'sí' if f.keep_exact else 'no'} | {html.escape(f.placement)} |"
        for f in c.furniture
    )
    parts = [
        f"#### v{brief.version} · {brief.status}"
        + (" · editado por ti" if brief.edited_by_user else ""),
        f"**{html.escape(c.title)}**",
        html.escape(c.summary),
        "**Restricciones espaciales**",
        _bullets(c.spatial_constraints),
        "**Mobiliario**",
        "| Mueble | Medidas (cm) | Exacto | Ubicación |\n|---|---|---|---|\n" + furniture
        if furniture
        else "_(ninguno)_",
        f"**Paleta:** {html.escape(', '.join(c.palette))}",
        f"**Materiales:** {html.escape('; '.join(c.materials))}",
        f"**Luz:** {html.escape(c.lighting)}",
        f"**Cámara:** {html.escape(c.camera)}",
    ]
    if c.open_questions:
        parts += ["**❓ Preguntas abiertas** (respóndelas al rechazar o edita el brief)",
                  _bullets(c.open_questions)]  # fmt: skip
    if brief.feedback:
        parts += [f"**Tus comentarios al rechazarlo:** {html.escape(brief.feedback)}"]
    if brief.warnings:
        parts += ["**Avisos**", _bullets(brief.warnings)]
    return "\n\n".join(parts)


def _dims(d: DimensionsCm) -> str:
    """Ancho x fondo x alto en cm; `?` lo desconocido (nunca se inventa)."""
    return " x ".join("?" if v is None else f"{v:g}" for v in (d.width_cm, d.depth_cm, d.height_cm))


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
    """Referencias para el render final (sin las capturas y planos de la v1, B-028)."""
    return [
        (a.original_name, str(a.id))
        for a in project.assets
        if a.kind is AssetKind.REFERENCIA and a.legacy_kind is None
    ]


def render_detail_md(project: ProjectMetadata, render: RenderRecord | None) -> str:
    if render is None:
        return "_Selecciona una imagen de cualquier etapa para verla aquí._"
    names = {a.id: a.original_name for a in project.assets}
    labels = {r.id: f"{r.stage.label} {r.id.hex[:8]}" for r in project.renders}
    inputs = ", ".join(labels.get(i) or names.get(i, str(i)[:8]) for i in render.input_asset_ids)
    lines = [
        f"#### {render.stage.label} `{render.id.hex[:8]}` · {render.status}",
        f"{render.size} · calidad {render.quality or '—'} · {render.deployment} · "
        f"coste {euros(render.cost_eur)} · {render.created_at:%d/%m/%Y %H:%M} UTC",
        f"**Entradas:** {html.escape(inputs)}",
    ]
    if render.inpaint:
        info = render.inpaint
        method = "máscara" if info.method == "mascara" else "imagen regenerada y recortada"
        source = info.source_render_id.hex[:8]
        lines.append(
            f"**Retoque de** `{source}`: «{html.escape(info.instruction)}» · "
            f"zona {info.coverage:.0%} · {method}"
        )
    if render.raw_of_render_id:
        lines.append(
            f"**Salida en bruto del retoque** `{render.raw_of_render_id.hex[:8]}`: la imagen "
            "completa que generó el modelo, sin recomponer (coste ya contado en el retoque)"
        )
    if render.previous_attempt_id:
        lines.append(
            f"**Sustituye a:** `{render.previous_attempt_id.hex[:8]}` (rechazado en la v1)"
        )
    if render.feedback:
        lines.append(f"**Tus comentarios al rechazarla (v1):** {html.escape(render.feedback)}")
    lines.append(
        f"<details><summary>Prompt usado</summary>\n\n```\n{render.prompt}\n```\n</details>"
    )
    return "\n\n".join(lines)


def audit_markdown(audit: RenderAudit | None) -> str:
    if audit is None:
        return "_Sin auditoría. Es opcional: compara la imagen con tu captura de SketchUp._"
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
            "<details><summary>Correcciones propuestas (se aplican al rechazar)</summary>\n\n"
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


def inpaint_file_captions(render: RenderRecord | None) -> list[tuple[str, str]]:
    """Archivos de un retoque para el visor: (nombre en `renders_historico/`, pie). La salida
    en bruto y la guía solo existen en los retoques de la v1."""
    info = render.inpaint if render else None
    if info is None:
        return []
    files = [
        (info.raw_file, "Salida en bruto del modelo (v1, antes de recomponer)"),
        (info.guide_file, "Guía enviada al renderizador (v1, zona en rojo)"),
        (info.mask_file, "Máscara (blanco = zona retocada)"),
    ]
    return [(name, caption) for name, caption in files if name]
