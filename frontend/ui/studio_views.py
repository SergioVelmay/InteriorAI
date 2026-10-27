"""Presentación pura de Bocetos, Composición y Render Final (sin Gradio): imágenes, costes,
auditoría y retoques.

Desde el Paso 22 no hay brief: cada generación guarda su prompt automático
(`RenderRecord.prompt_info`). Desde el Paso 23 son pestañas de primer nivel y lo que recibe cada
generación sigue las reglas de `shared.supports` (las mismas que aplica el backend).
"""

from __future__ import annotations

import html
import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

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
from shared.sizes import RENDERER_SIZES
from shared.supports import (
    MAX_SUPPORTS,
    draft_base,
    geometric_references,
    split_supports,
)

# Coste estimado por acción (EUR, límite alto de lo observado en las pruebas reales).
# Modelos GPT de imagen (Paso 22, medido con 3 imágenes de entrada en calidad media: 4 bocetos
# = 0,142 € y 5 = 0,177 €): cada imagen de entrada ≈ 0,042 € (tokens de imagen, lo que más
# pesa) y cada imagen generada según su calidad, más el prompt.
COST_DRAFT_INPUT = 0.042
COST_DRAFT_OUTPUT = {"low": 0.003, "medium": 0.009, "high": 0.035}
COST_PROMPT = 0.002  # el PROMPT_ARCHITECT escribe el prompt de cada generación (luna)
# Composición y retoque (Paso 23, medido: 4 imágenes de entrada en calidad media = 0,047 € cada
# uno): el COMPOSITION_BUILDER factura mucho menos por imagen de entrada que el de bocetos.
COST_COMPOSITION_INPUT = 0.010
# Render final (FLUX, precios de config/pricing.yaml): el primer MP de la imagen generada, el
# resto de MP y la imagen de partida (1 MP por imagen de entrada); el MP de la factura es binario.
COST_RENDER_FIRST_MP = 0.0264
COST_RENDER_EXTRA_MP = 0.0132
COST_RENDER_INPUT = 0.0132
RATIOS = list(RENDERER_SIZES)  # 16:9, 3:2 (por defecto), 1:1, 2:3, 9:16
MAX_INPUTS = 1 + MAX_SUPPORTS  # imagen base o de partida + apoyos (Paso 23)
# Retoque: solo la composición, con máscara nativa (B-038).
COST_INPAINT = {RenderStage.COMPOSITION: 0.035}
INPAINT_STAGES = frozenset(COST_INPAINT)
COST_AUDIT = 0.25
CONFIRM_THRESHOLD_EUR = 0.20  # en modo azure, por encima se pide un segundo clic (B-043)

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
    """Coste estimado de `n` imágenes de un modelo GPT de imagen (bocetos, composiciones y
    retoques) con `inputs` imágenes de entrada."""
    inputs = min(inputs, MAX_INPUTS)
    return COST_PROMPT + inputs * COST_DRAFT_INPUT + n * COST_DRAFT_OUTPUT.get(quality, 0.009)


def _dims(d: Any) -> str:
    """Ancho x fondo x alto en cm; `?` lo desconocido (nunca se inventa)."""
    return " x ".join("?" if v is None else f"{v:g}" for v in (d.width_cm, d.depth_cm, d.height_cm))


# --- Referencias activas y lo que recibe cada generación ----------------------------------------


@dataclass(frozen=True)
class Thumb:
    """Miniatura con su pie: `tone` «start» (imagen base o de partida) o «excluded» (no cabe)."""

    path: Path
    caption: str
    tone: str = ""


def file_url(path: Path) -> str:
    """URL de Gradio para un archivo del volumen (`allowed_paths`)."""
    return "/gradio_api/file=" + quote(path.as_posix(), safe="/:")


def thumbs_html(items: list[Thumb], empty: str = "") -> str:
    """Tira de miniaturas en HTML: el pie de las que quedan fuera va en rojo (Paso 23)."""
    if not items:
        return f'<p class="iai-muted">{html.escape(empty)}</p>' if empty else ""
    cards = "".join(
        f'<figure class="iai-thumb {t.tone}" title="{html.escape(t.caption)}">'
        f'<img src="{file_url(t.path)}" alt="" loading="lazy">'
        f"<figcaption>{html.escape(t.caption)}</figcaption></figure>"
        for t in items
    )
    return f'<div class="iai-thumbs">{cards}</div>'


def _file(data_dir: Path, project: ProjectMetadata, asset: Asset) -> Path:
    return data_dir / str(project.id) / asset.kind.folder / asset.stored_name


def _excluded(data_dir: Path, project: ProjectMetadata, excluded: list[Asset]) -> list[Thumb]:
    return [
        Thumb(_file(data_dir, project, a), f"Fuera: máx. {MAX_SUPPORTS} apoyos · {a.original_name}",
              "excluded")
        for a in excluded
    ]  # fmt: skip


def draft_thumbs(project: ProjectMetadata, data_dir: Path) -> list[Thumb]:
    """Lo que reciben los bocetos: la imagen base, los apoyos y, en rojo, los que no caben."""
    base = draft_base(project)
    sent, excluded = split_supports(project, base)
    items = []
    if base is not None:
        items.append(Thumb(_file(data_dir, project, base), f"Base · {reference_summary(base)}",
                           "start"))  # fmt: skip
    items += [Thumb(_file(data_dir, project, a), reference_summary(a)) for a in sent]
    return items + _excluded(data_dir, project, excluded)


def support_thumbs(project: ProjectMetadata, data_dir: Path) -> list[Thumb]:
    """Apoyos de la composición y del retoque (los del espacio primero) y, en rojo, los que no
    caben."""
    sent, excluded = split_supports(project)
    items = [Thumb(_file(data_dir, project, a), reference_summary(a)) for a in sent]
    return items + _excluded(data_dir, project, excluded)


def render_thumb(
    project: ProjectMetadata, render: RenderRecord | None, data_dir: Path, caption: str
) -> list[Thumb]:
    asset = next((a for a in project.assets if render and a.id == render.id), None)
    if asset is None:
        return []
    return [Thumb(_file(data_dir, project, asset), caption, "start")]


def audit_thumbs(
    project: ProjectMetadata, draft: RenderRecord | None, data_dir: Path
) -> list[Thumb]:
    """Lo que compara la auditoría (B-046): las referencias del espacio y el boceto."""
    items = [Thumb(_file(data_dir, project, a), f"Espacio · {a.original_name}")
             for a in geometric_references(project)]  # fmt: skip
    return items + render_thumb(project, draft, data_dir, "Boceto auditado")


def excluded_count(project: ProjectMetadata) -> int:
    """Referencias activas que no caben como apoyo de los bocetos (aviso en Referencias)."""
    return len(split_supports(project, draft_base(project))[1])


def reference_summary(asset: Asset) -> str:
    """Pie de una referencia activa: lo que se usa de ella (grupos marcados)."""
    groups = asset.sheet.selected_elements() if asset.sheet else {}
    used = ", ".join(f"{RECIPE_GROUPS[g].split(' (')[0].lower()} ({len(e)})"
                     for g, e in groups.items())  # fmt: skip
    return f"{asset.original_name} · {used}"


def draft_inputs(project: ProjectMetadata) -> int:
    """Imágenes que recibiría el modelo de bocetos: la base y los apoyos que caben."""
    base = draft_base(project)
    return (base is not None) + len(split_supports(project, base)[0])


def final_cost(size: str, *, prompt: bool = True) -> float:
    """Coste estimado de un render final de `size`; «Otra versión» no escribe prompt."""
    width, height = (int(x) for x in size.split("x"))
    extra_mp = max(width * height / 1_048_576 - 1, 0)
    render = COST_RENDER_FIRST_MP + extra_mp * COST_RENDER_EXTRA_MP + COST_RENDER_INPUT
    return (COST_PROMPT if prompt else 0) + render


def resolution_choices(ratio: str) -> list[tuple[str, str]]:
    """Resoluciones de una proporción (Paso 24), de menor a mayor, con sus megapíxeles."""
    choices = []
    for size in RENDERER_SIZES[ratio]:
        width, height = (int(x) for x in size.split("x"))
        choices.append((f"{width} x {height} · {width * height / 1e6:.1f} MP", size))
    return choices


def composition_cost(quality: str, inputs: int) -> float:
    """Coste estimado de una composición o un retoque con `inputs` imágenes de entrada."""
    inputs = min(inputs, MAX_INPUTS)
    return COST_PROMPT + inputs * COST_COMPOSITION_INPUT + COST_DRAFT_OUTPUT.get(quality, 0.009)


def composition_inputs(project: ProjectMetadata) -> int:
    """Imágenes de una composición o un retoque: la de partida y los apoyos que caben."""
    return 1 + len(split_supports(project)[0])


# --- Renders ---------------------------------------------------------------------------------


def renders_of(project: ProjectMetadata, stage: RenderStage) -> list[RenderRecord]:
    return sorted(
        (r for r in project.renders if r.stage is stage), key=lambda r: r.created_at, reverse=True
    )


def render_caption(render: RenderRecord) -> str:
    audit = ""
    if render.audits:
        audit = f" · auditoría {render.audits[-1].report.score}/100"
    retouch = " · retoque" if render.inpaint else ""
    return (
        f"{STATUS_ICONS[render.status]} {render.status}{retouch}{audit} · {euros(render.cost_eur)}"
    )


def selected_choices(project: ProjectMetadata, stage: RenderStage) -> list[tuple[str, str]]:
    return [
        (f"{r.stage.label} {r.id.hex[:8]} · {r.created_at:%d/%m %H:%M}", str(r.id))
        for r in renders_of(project, stage)
        if r.status is RenderStatus.SELECTED
    ]


def selected_render(project: ProjectMetadata, stage: RenderStage) -> RenderRecord | None:
    """La imagen seleccionada de una etapa (una como mucho, B-043)."""
    return next((r for r in renders_of(project, stage) if r.status is RenderStatus.SELECTED), None)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {html.escape(i)}" for i in items)


def size_label(size: str) -> str:
    """«2448x1632 (3:2)» (B-078); sin proporción si no es sencilla (p. ej. 1920x1088)."""
    width, height = (int(v) for v in size.split("x"))
    divisor = math.gcd(width, height)
    ratio = f"{width // divisor}:{height // divisor}"
    simple = width // divisor <= 21 and height // divisor <= 21
    return f"{width}×{height}" + (f" ({ratio})" if simple else "")  # noqa: RUF001


def render_title_md(render: RenderRecord | None) -> str:
    """Línea bajo la imagen grande: etapa, estado, tamaño con su proporción, calidad (los
    modelos que la tienen; el renderizador no) y coste."""
    if render is None:
        return "_Genera o elige una imagen para verla aquí._"
    state = "seleccionado" if render.status is RenderStatus.SELECTED else "sin seleccionar"
    quality = f" · calidad {render.quality}" if render.quality else ""
    return (
        f"**{render.stage.label} `{render.id.hex[:8]}`** · {STATUS_ICONS[render.status]} {state}"
        f" · {size_label(render.size)}{quality} · {euros(render.cost_eur)} · "
        f"{render.created_at:%d/%m/%Y %H:%M} UTC"
    )


def render_detail_md(project: ProjectMetadata, render: RenderRecord | None) -> str:
    """«Ver más» (B-036, B-047): lo que entendió el PROMPT_ARCHITECT, el prompt enviado y el
    resto de la trazabilidad. Las imágenes de la v1 no tienen prompt automático (Paso 33)."""
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
    else:
        lines.append("Imagen de la v1: anterior al prompt automático.")
    lines.append(f"**Entradas:** {html.escape(inputs)} · {render.deployment}")
    if render.inpaint:
        info_inpaint = render.inpaint
        lines.append(
            f"**Retoque de** `{info_inpaint.source_render_id.hex[:8]}`: "
            f"«{html.escape(info_inpaint.instruction)}» · zona {info_inpaint.coverage:.0%} · "
            "máscara"
        )
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


def audit_markdown(audit: RenderAudit | None, project: ProjectMetadata | None = None) -> str:
    if audit is None:
        return (
            "_Sin auditoría con IA. Es opcional: compara el boceto con las referencias que "
            "marcan perspectiva o geometría._"
        )
    r = audit.report
    names = {a.id: a.original_name for a in project.assets} if project else {}
    compared = ", ".join(names.get(i, str(i)[:8]) for i in audit.reference_asset_ids)
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
        f"{audit.reasoning_effort} · {euros(audit.cost_eur)} · {audit.created_at:%d/%m %H:%M} UTC"
        + (f" · comparado con: {html.escape(compared)}" if compared else ""),
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
            "<details><summary>Correcciones propuestas (se usan con «Usar la auditoría»)"
            "</summary>"
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
