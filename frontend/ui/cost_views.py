"""Presentación pura de la pestaña Costes (sin Gradio): indicadores, tablas para los gráficos,
registro de llamadas, CSV y tabla de precios."""

from __future__ import annotations

import csv
import html
import io
from typing import Any

import pandas as pd

from shared.roles import Role

ALL = "Todos"
STATUS_LABELS = {"ok": "correcta", "error": "error"}
ROLE_COLORS = {  # colores estables por rol en todos los gráficos
    Role.PROMPT_ENGINEER.value: "#a1a1aa",
    Role.REFERENCE_ANALYST.value: "#71717a",
    Role.FAST_DRAFT.value: "#38bdf8",
    Role.STRUCTURAL_COMPOSER.value: "#818cf8",
    Role.PHOTOREALISTIC_RENDERER.value: "#f59e0b",
    Role.GEOMETRIC_AUDITOR.value: "#f43f5e",
}
RECORD_COLUMNS = [
    "Fecha (UTC)", "Proyecto", "Rol", "Operación", "Estado", "Coste (€)", "Latencia (s)",
    "Tokens entrada", "Tokens salida", "MP generados", "Simulada", "Petición",
]  # fmt: skip


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
        "Coste **estimado** con los precios de lista de `pricing.yaml`; la cifra real está en "
        "Azure Cost Management."
    ]
    if summary["simulated_excluded"]:
        parts.append(
            f"{summary['simulated_excluded']} llamada(s) simulada(s) ocultas "
            "(marca «Incluir simulación» para verlas)."
        )
    elif summary["includes_simulated"]:
        parts.append("Incluye llamadas **simuladas** (modo mock: sin coste real).")
    if summary["totals"]["unpriced_calls"]:
        parts.append(f"{summary['totals']['unpriced_calls']} llamada(s) sin precio configurado.")
    if summary["totals"]["errors"]:
        parts.append(
            "Las llamadas con error figuran a 0 €, aunque el proveedor pudo facturarlas "
            "(p. ej. un timeout)."
        )
    return " ".join(parts)


def role_frame(summary: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Rol": g["key"], "Coste (€)": g["cost_eur"], "Llamadas": g["calls"]}
         for g in summary["by_role"]],
        columns=["Rol", "Coste (€)", "Llamadas"],
    )  # fmt: skip


def project_frame(summary: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Proyecto": g["label"] or g["key"][:8], "Coste (€)": g["cost_eur"]}
         for g in summary["by_project"]],
        columns=["Proyecto", "Coste (€)"],
    )  # fmt: skip


def y_range(frame: pd.DataFrame, column: str = "Coste (€)") -> list[float]:
    """Eje Y desde 0: con un único valor, el gráfico no dibujaría la barra."""
    top = float(frame[column].max()) if not frame.empty else 0.0
    return [0.0, round(top * 1.15, 6) or 0.01]


def day_role_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Coste por día y rol (barras apiladas) a partir de los registros."""
    totals: dict[tuple[str, str], float] = {}
    for record in records:
        key = (record["timestamp"][:10], record["role"])
        totals[key] = totals.get(key, 0.0) + (record["cost_eur"] or 0.0)
    return pd.DataFrame(
        [{"Día": day, "Rol": role, "Coste (€)": round(cost, 6)}
         for (day, role), cost in sorted(totals.items())],
        columns=["Día", "Rol", "Coste (€)"],
    )  # fmt: skip


def filter_records(
    records: list[dict[str, Any]], role: str | None, status: str | None
) -> list[dict[str, Any]]:
    return [
        r
        for r in records
        if (not role or role == ALL or r["role"] == role)
        and (not status or status == ALL or r["status"] == status)
    ]


def records_frame(records: list[dict[str, Any]], with_project: bool = True) -> pd.DataFrame:
    """Tabla de llamadas; la columna «Proyecto» solo tiene sentido con todos los proyectos."""
    rows = [
        [
            r["timestamp"][:19].replace("T", " "),
            r.get("project_name") or "",
            r["role"],
            r["operation"],
            STATUS_LABELS.get(r["status"], r["status"])
            + (f" ({r['error_type']})" if r.get("error_type") else ""),
            None if r["cost_eur"] is None else round(r["cost_eur"], 4),
            round(r["latency_s"], 1),
            r["input_tokens"],
            r["output_tokens"],
            round(r["megapixels_out"], 2),
            "sí" if r["simulated"] else "no",
            r.get("request_id") or "",
        ]
        for r in records
    ]
    frame = pd.DataFrame(rows, columns=RECORD_COLUMNS)
    return frame if with_project else frame.drop(columns="Proyecto")


def records_csv(records: list[dict[str, Any]]) -> str:
    """CSV separado por `;` (lo abre bien una hoja de cálculo en español)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(RECORD_COLUMNS)
    writer.writerows(records_frame(records).itertuples(index=False))
    return buffer.getvalue()


def pricing_frame(pricing: dict[str, Any] | None) -> pd.DataFrame:
    """Una fila por despliegue con sus tarifas (EUR por millón de tokens o por MP)."""
    rows = []
    tier = (pricing or {}).get("deployment_type", "global")
    for name, spec in ((pricing or {}).get("deployments") or {}).items():
        kind = spec.get("type")
        if kind == "tokens":
            short = spec["rates"][tier]["short"]
            rates = (f"entrada {short['input']} · caché {short['cached_input']} · "
                     f"salida {short['output']} (€/M tokens)")  # fmt: skip
        elif kind == "image_tokens":
            rates = (f"texto {spec['input_text']} · imagen {spec['input_image']} · "
                     f"salida {spec['output_image']} (€/M tokens)")  # fmt: skip
        else:
            rates = (f"1.er MP {spec['initial_mp']} · MP adicional {spec['additional_mp']} · "
                     f"MP de referencia {spec['reference_mp']} (€)")  # fmt: skip
        rows.append({"Despliegue": name, "Tipo": kind, "Tarifas": rates})
    return pd.DataFrame(rows, columns=["Despliegue", "Tipo", "Tarifas"])


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
