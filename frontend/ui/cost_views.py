"""Presentación pura de la pestaña Costes IA (sin Gradio): indicadores, gráficos (Altair),
registro de llamadas con su detalle, CSV y tabla de precios. Solo gasto real (B-031)."""

from __future__ import annotations

import csv
import html
import io
import json
from typing import Any

import altair as alt
import pandas as pd

from shared.roles import Role

ALL = "Todos"
STATUS_LABELS = {"ok": "correcta", "error": "error"}
# Un color vivo y muy distinto por rol (B-080), el mismo en todos los gráficos; en el orden de
# la leyenda, que sigue el flujo: referencias → prompts → bocetos → composición → render final
# → auditoría.
ROLE_COLORS = {
    Role.REFERENCE_ANALYST.value: "#22c55e",  # verde
    Role.PROMPT_ARCHITECT.value: "#a855f7",  # morado
    Role.FAST_DRAFT_MAKER.value: "#3b82f6",  # azul
    Role.COMPOSITION_BUILDER.value: "#facc15",  # amarillo
    Role.REALISTIC_RENDERER.value: "#f97316",  # naranja
    Role.GEOMETRY_AUDITOR.value: "#ef4444",  # rojo
}
# Tabla del registro (B-033): lo esencial; el resto, en el detalle de la fila y en el CSV.
RECORD_COLUMNS = [
    "Fecha (UTC)", "Proyecto", "Rol", "Despliegue", "Estado", "Coste (€)", "Latencia (s)",
    "Tokens entrada", "Tokens salida", "MPx generados", "MPx referencia",
]  # fmt: skip
# CSV: todas las columnas, también las que la tabla no muestra (decisión del usuario).
CSV_COLUMNS = [
    "Fecha (UTC)", "Proyecto", "Rol", "Rol en la llamada", "Despliegue", "Operación", "Estado",
    "Error", "Coste (€)", "Desglose del coste", "Tarifa", "Latencia (s)", "Tokens entrada",
    "Tokens en caché", "Tokens escritos en caché", "Tokens de texto", "Tokens de imagen",
    "Tokens salida", "Tokens de razonamiento", "Imágenes", "MPx generados", "MPx referencia",
    "Petición", "Id",
]  # fmt: skip

# Gráficos en el tema oscuro de la app.
_AXIS = {"labelColor": "#a1a1aa", "titleColor": "#a1a1aa", "gridColor": "#27272a",
         "domainColor": "#3f3f46", "tickColor": "#3f3f46", "labelFontSize": 12,
         "titleFontSize": 12}  # fmt: skip
_LABEL_CHARS = 90  # caracteres de etiquetas que caben en horizontal en media pantalla


def money(value: float | None) -> str:
    return "—" if value is None else f"{value:.4f} €"


def kpi_html(summary: dict[str, Any]) -> str:
    totals = summary["totals"]
    calls = totals["calls"]
    average = totals["latency_s"] / calls if calls else 0.0
    cards = [
        ("Coste estimado", money(totals["cost_eur"])),
        ("Llamadas", f"{calls}"),
        ("Errores", f"{totals['errors']}"),
        ("Imágenes", f"{totals['images_out']}"),
        ("Megapíxeles", f"{totals['megapixels_out']:.2f}"),
        ("Latencia media", f"{average:.1f} s"),
    ]
    items = "".join(
        f'<div class="iai-kpi"><span>{html.escape(label)}</span><strong>{value}</strong></div>'
        for label, value in cards
    )
    return f'<div class="iai-kpis">{items}</div>'


def notes_md(summary: dict[str, Any]) -> str:
    parts = [
        "Gasto **real** (sin las llamadas simuladas del modo mock), **estimado** con los precios "
        "de lista de `pricing.yaml`; la cifra facturada está en Azure Cost Management."
    ]
    if not summary["totals"]["calls"]:
        parts.append("Todavía no hay llamadas reales a la IA.")
    if summary["totals"]["unpriced_calls"]:
        parts.append(f"{summary['totals']['unpriced_calls']} llamada(s) sin precio configurado.")
    if summary["totals"]["errors"]:
        parts.append(
            "Las llamadas con error figuran a 0 €, aunque el proveedor pudo facturarlas "
            "(p. ej. un timeout)."
        )
    return " ".join(parts)


# --- Gráficos (B-032, B-080, B-081) ------------------------------------------------------------
# Una serie por rol actual (Paso 26): cada llamada cuenta en el rol que hoy tiene su despliegue
# (lo hace el backend). La leyenda es única y va fuera de los gráficos (`legend_html`).

# Ancho fijo: `gr.Plot` no da tamaño al contenedor y `width="container"` deja el gráfico vacío.
# Media columna (coste por rol, junto a la leyenda) y ancho completo (por día y por proyecto).
HALF_WIDTH, FULL_WIDTH = 520, 1160


def _finish(chart: alt.Chart, title: str, width: int, height: int = 260) -> alt.Chart:
    return (
        chart.properties(title=title, width=width, height=height)
        .configure(background="transparent")
        .configure_axis(**_AXIS)
        .configure_title(color="#e4e4e7", fontSize=14)
        .configure_view(stroke=None)
    )


def _angle(labels: list[str], chars: int = _LABEL_CHARS) -> int:
    """Etiquetas en horizontal mientras quepan; si no, giradas (B-032)."""
    return 0 if sum(len(label) + 2 for label in labels) <= chars else -40


def _color() -> alt.Color:
    """Siempre los seis roles con sus colores; sin leyenda (la hay común, fuera)."""
    return alt.Color(
        "Rol:N",
        scale=alt.Scale(domain=list(ROLE_COLORS), range=list(ROLE_COLORS.values())),
        legend=None,
    )


def legend_html(summary: dict[str, Any]) -> str:
    """Leyenda común de todos los gráficos (B-081): cada rol con su despliegue actual."""
    deployments = summary.get("role_deployments") or {}
    items = "".join(
        f'<li><span class="iai-swatch" style="background:{color}"></span>'
        f"<strong>{html.escape(role)}</strong>"
        + (f" <span>({html.escape(deployments[role])})</span>" if deployments.get(role) else "")
        + "</li>"
        for role, color in ROLE_COLORS.items()
    )
    return f'<div class="iai-legend"><h4>Rol (despliegue actual)</h4><ul>{items}</ul></div>'


def role_frame(summary: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Rol": g["key"], "Coste (€)": g["cost_eur"], "Llamadas": g["calls"]}
         for g in summary.get("by_role", [])],
        columns=["Rol", "Coste (€)", "Llamadas"],
    )  # fmt: skip


def role_chart(summary: dict[str, Any]) -> alt.Chart:
    """Coste por rol, en el orden de la leyenda."""
    frame = role_frame(summary)
    chart = (
        alt.Chart(frame)
        .mark_bar()
        .encode(
            x=alt.X("Rol:N", title=None, sort=list(ROLE_COLORS),
                    axis=alt.Axis(labelAngle=-40, labelAlign="right", labelLimit=0)),
            y=alt.Y("Coste (€):Q", scale=alt.Scale(domainMin=0)),
            color=_color(),
            tooltip=["Rol", alt.Tooltip("Coste (€):Q", format=".4f"), "Llamadas"],
        )
    )  # fmt: skip
    return _finish(chart, "Coste por rol", HALF_WIDTH, height=300)


def _stacked(groups: list[dict[str, Any]], column: str, label: bool = False) -> pd.DataFrame:
    """Desglose cruzado del backend (`by_day_role`, `by_project_role`) → filas para apilar."""
    return pd.DataFrame(
        [{column: (g["label"] or g["key"][:8]) if label else g["key"], "Rol": g["role"],
          "Coste (€)": g["cost_eur"], "Llamadas": g["calls"]}
         for g in groups],
        columns=[column, "Rol", "Coste (€)", "Llamadas"],
    )  # fmt: skip


def _stacked_chart(frame: pd.DataFrame, column: str, title: str) -> alt.Chart:
    labels = list(dict.fromkeys(frame[column]))
    chart = (
        alt.Chart(frame)
        .mark_bar()
        .encode(
            x=alt.X(f"{column}:N", title=None, sort=labels,
                    axis=alt.Axis(labelAngle=_angle(labels, _LABEL_CHARS * 2), labelLimit=0)),
            y=alt.Y("sum(Coste (€)):Q", title="Coste (€)", scale=alt.Scale(domainMin=0)),
            color=_color(),
            order=alt.Order("Orden:Q"),
            tooltip=[column, "Rol", alt.Tooltip("Coste (€):Q", format=".4f"), "Llamadas"],
        )
        .transform_calculate(Orden=f"indexof({list(ROLE_COLORS)}, datum.Rol)")
    )  # fmt: skip
    return _finish(chart, title, FULL_WIDTH, height=300)


def day_frame(summary: dict[str, Any]) -> pd.DataFrame:
    return _stacked(summary.get("by_day_role", []), "Día")


def day_chart(summary: dict[str, Any]) -> alt.Chart:
    """Coste por día, apilado por rol (B-081): a ancho completo, crece con los días."""
    return _stacked_chart(day_frame(summary), "Día", "Coste por día")


def project_frame(summary: dict[str, Any]) -> pd.DataFrame:
    return _stacked(summary.get("by_project_role", []), "Proyecto", label=True)


def project_chart(summary: dict[str, Any]) -> alt.Chart:
    """Coste por proyecto, apilado por rol (B-081)."""
    return _stacked_chart(project_frame(summary), "Proyecto", "Coste por proyecto")


# --- Registro de llamadas (B-033) -----------------------------------------------------------------


def filter_records(
    records: list[dict[str, Any]], role: str | None, status: str | None
) -> list[dict[str, Any]]:
    return [
        r
        for r in records
        if (not role or role == ALL or r["role"] == role)
        and (not status or status == ALL or r["status"] == status)
    ]


def _when(record: dict[str, Any]) -> str:
    return record["timestamp"][:19].replace("T", " ")


def _cost(record: dict[str, Any]) -> float | None:
    return None if record["cost_eur"] is None else round(record["cost_eur"], 4)


# Anchos de la tabla (B-033): ajustados al contenido para que no haga falta desplazarse.
_COLUMN_WIDTHS = {
    "Fecha (UTC)": 11, "Proyecto": 14, "Rol": 18, "Despliegue": 15, "Estado": 5,
    "Coste (€)": 6, "Latencia (s)": 6, "Tokens entrada": 6, "Tokens salida": 6,
    "MPx generados": 7, "MPx referencia": 7,
}  # fmt: skip


def column_widths(with_project: bool) -> list[str]:
    widths = {k: v for k, v in _COLUMN_WIDTHS.items() if with_project or k != "Proyecto"}
    total = sum(widths.values())
    return [f"{100 * v / total:.1f}%" for v in widths.values()]


def records_frame(records: list[dict[str, Any]], with_project: bool = True) -> pd.DataFrame:
    """Tabla de llamadas; la columna «Proyecto» solo tiene sentido con todos los proyectos."""
    rows = [
        [
            _when(r),
            r.get("project_name") or "",
            r["role"],
            r["deployment"],
            "✓" if r["status"] == "ok" else "error",  # el error concreto, en el detalle
            _cost(r),
            round(r["latency_s"], 1),
            r["input_tokens"],
            r["output_tokens"],
            round(r.get("megapixels_out", 0.0), 2),
            round(r.get("megapixels_ref", 0.0), 2),
        ]
        for r in records
    ]
    frame = pd.DataFrame(rows, columns=RECORD_COLUMNS)
    return frame if with_project else frame.drop(columns="Proyecto")


def _breakdown(record: dict[str, Any]) -> str:
    parts = record.get("cost_breakdown") or {}
    return ", ".join(f"{key} {value:.6f}" for key, value in parts.items())


def record_detail_md(record: dict[str, Any] | None) -> str:
    """«Ver más» de una fila del registro: todo lo que no cabe en la tabla."""
    if record is None:
        return "_Selecciona una fila del registro para ver el detalle de la llamada._"
    breakdown = _breakdown(record) or "—"
    call_role = record.get("call_role") or record["role"]
    lines = [
        f"#### {html.escape(record['role'])} · {html.escape(record['deployment'])} · "
        f"{_when(record)} UTC",
        f"- **Proyecto:** {html.escape(record.get('project_name') or '—')}",
        f"- **Operación:** `{record['operation']}` · **estado:** "
        f"{STATUS_LABELS.get(record['status'], record['status'])}"
        + (f" (`{record['error_type']}`)" if record.get("error_type") else ""),
        f"- **Coste:** {money(record['cost_eur'])} · tarifa `{record.get('pricing_tier') or '—'}`"
        f" · desglose: {html.escape(breakdown)}",
        f"- **Tokens:** entrada {record['input_tokens']} (en caché "
        f"{record.get('cached_input_tokens', 0)}, escritos en caché "
        f"{record.get('cache_write_tokens', 0)}; texto {record.get('input_text_tokens', 0)}, "
        f"imagen {record.get('input_image_tokens', 0)}) · salida {record['output_tokens']} "
        f"(razonamiento {record.get('reasoning_tokens', 0)})",
        f"- **Imágenes:** {record.get('images_out', 0)} · MPx generados "
        f"{record.get('megapixels_out', 0.0):.4f} · MPx de referencia "
        f"{record.get('megapixels_ref', 0.0):.4f}",
        f"- **Latencia:** {record['latency_s']:.2f} s · **petición:** "
        f"`{record.get('request_id') or '—'}` · **id:** `{record['id']}`",
    ]
    if call_role != record["role"]:  # su despliegue es hoy de otro rol (Paso 26)
        lines.insert(1, f"- **Rol en la llamada:** {html.escape(call_role)} (hoy, su "
                        f"despliegue lo usa {html.escape(record['role'])})")  # fmt: skip
    return "\n".join(lines)


def records_csv(records: list[dict[str, Any]]) -> str:
    """CSV separado por `;` (lo abre bien una hoja de cálculo en español), con todo el detalle."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(CSV_COLUMNS)
    for r in records:
        writer.writerow([
            _when(r), r.get("project_name") or "", r["role"], r.get("call_role") or r["role"],
            r["deployment"], r["operation"],
            STATUS_LABELS.get(r["status"], r["status"]), r.get("error_type") or "", _cost(r),
            json.dumps(r.get("cost_breakdown") or {}, ensure_ascii=False),
            r.get("pricing_tier") or "", round(r["latency_s"], 3), r["input_tokens"],
            r.get("cached_input_tokens", 0), r.get("cache_write_tokens", 0),
            r.get("input_text_tokens", 0), r.get("input_image_tokens", 0), r["output_tokens"],
            r.get("reasoning_tokens", 0), r.get("images_out", 0),
            round(r.get("megapixels_out", 0.0), 4), round(r.get("megapixels_ref", 0.0), 4),
            r.get("request_id") or "", r["id"],
        ])  # fmt: skip
    return buffer.getvalue()


def project_calls_md(records: list[dict[str, Any]]) -> str:
    """Llamadas del proyecto en su resumen (B-027): tabla breve que cabe en media pantalla."""
    if not records:
        return "_Sin llamadas reales de IA._"
    rows = []
    for r in records:
        stamp = r["timestamp"]  # ISO: 2026-10-24T22:48:19Z → 24/10/26 22:48
        when = f"{stamp[8:10]}/{stamp[5:7]}/{stamp[2:4]} {stamp[11:16]}"
        status = "✓" if r["status"] == "ok" else "error"
        cost = "—" if r["cost_eur"] is None else f"{r['cost_eur']:.4f}"
        rows.append(f"| {when} | {r['role']} | {status} | {cost} |")
    return "\n".join(["| Fecha (UTC) | Rol | Estado | Coste (€) |", "|---|---|---|---:|", *rows])


# --- Precios (B-034) ------------------------------------------------------------------------------

PRICING_COLUMNS = ["Despliegue", "Tipo", "Tarifa 1", "Tarifa 2", "Tarifa 3", "Unidades"]


def _rate(name: str, value: float) -> str:
    return f"{name} {value:g}".replace(".", ",")


def pricing_frame(pricing: dict[str, Any] | None) -> pd.DataFrame:
    """Una fila por despliegue: sus tres tarifas en columnas y las unidades aparte."""
    rows = []
    tier = (pricing or {}).get("deployment_type", "global")
    for name, spec in ((pricing or {}).get("deployments") or {}).items():
        kind = spec.get("type")
        if kind == "tokens":
            short = spec["rates"][tier]["short"]
            rates = [("entrada", short["input"]), ("caché", short["cached_input"]),
                     ("salida", short["output"])]  # fmt: skip
            units = "€/M tokens"
        elif kind == "image_tokens":
            rates = [("texto", spec["input_text"]), ("imagen", spec["input_image"]),
                     ("salida", spec["output_image"])]  # fmt: skip
            units = "€/M tokens"
        else:
            rates = [("1.er MPx", spec["initial_mp"]), ("MPx adicional", spec["additional_mp"]),
                     ("MPx de referencia", spec["reference_mp"])]  # fmt: skip
            units = "€/MPx"
        rows.append([name, kind, *(_rate(label, value) for label, value in rates), units])
    return pd.DataFrame(rows, columns=PRICING_COLUMNS)


def chain_cost_md(cost: dict[str, Any] | None) -> str:
    """Línea del visor del Estudio: lo que ha costado llegar a esta imagen."""
    if cost is None:
        return ""
    totals = cost["totals"]
    text = (
        f"**Coste acumulado de la cadena:** {money(totals['cost_eur'])} · "
        f"{totals['calls']} llamada(s) (fichas de referencias, brief, etapas, retoques y "
        "auditorías que llevan a esta imagen; sin ramas descartadas)"
    )
    if cost["simulated_calls"]:
        text += f" · simulación: {cost['simulated_calls']} llamada(s) sin coste real"
    return text


def alert_lines(alerts: dict[str, Any] | None, project_id: str | None) -> list[str]:
    """Avisos de gasto real (B-021): del proyecto indicado (o, sin proyecto, de todos los que
    superan su umbral) y del total. Vacío si no se supera nada."""
    if not alerts:
        return []
    lines = []
    projects = [p for p in alerts["projects"] if p["exceeded"]]
    if project_id is not None:
        projects = [p for p in projects if p["project_id"] == project_id]
        lines += [
            f"⚠️ Este proyecto lleva {p['cost_eur']:.2f} € de IA "
            f"(aviso a partir de {p['threshold_eur']:g} €)."
            for p in projects
        ]
    elif projects:
        names = ", ".join(f"{p['name']} ({p['cost_eur']:.2f} €)" for p in projects)
        limit = projects[0]["threshold_eur"]
        lines.append(f"⚠️ Proyectos por encima de {limit:g} €: {names}.")
    total = alerts["total"]
    if total["exceeded"]:
        lines.append(
            f"⚠️ El gasto total de IA es {total['cost_eur']:.2f} € "
            f"(aviso a partir de {total['threshold_eur']:g} €)."
        )
    return lines
