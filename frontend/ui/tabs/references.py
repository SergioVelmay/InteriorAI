"""Pestaña Referencias: las imágenes del proyecto activo, todas referencias (B-028).

Cada imagen se sube con sus notas y se analiza al momento, de una en una (B-029): el
REFERENCE_ANALYST devuelve su receta y la ficha queda guardada con lo que piden las notas ya
marcado. La ficha es un formulario de casillas de dos niveles (grupo → elementos) con «Marcar
todo», «Desmarcar todo» y «Guardar ficha» (B-030). Una referencia no se borra: se descarta
desmarcando todo y se reactiva marcando algo. Solo las activas se usan en el diseño.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
import gradio as gr

from shared.models import RECIPE_GROUPS, Asset, AssetKind
from shared.supports import MAX_SUPPORTS
from ui.api_client import ApiError, BackendClient
from ui.covers import asset_path, placeholder
from ui.forecast import FORECAST_S
from ui.money import euros_up
from ui.studio_views import excluded_count
from ui.views import (
    COST_ANALYSIS,
    asset_caption,
    asset_info_md,
    selected_ids,
    sheet_groups,
    sheet_status,
    sheet_tooltips,
    tooltips_html,
)

FILE_TYPES = [".png", ".jpg", ".jpeg", ".webp"]
NO_PROJECT = "Ningún proyecto activo: elige o crea uno en la pestaña **Proyectos**."
NO_SELECTION = "Selecciona una imagen de la galería para ver su ficha."
ANALYSIS_HINT = (
    "Se analiza al subirla (REFERENCE_ANALYST, unos 30-60 s): en Azure ≈ "
    f"{euros_up(COST_ANALYSIS)} por imagen; en simulación, sin coste. Las notas orientan el "
    "análisis: en qué fijarse, qué priorizar o cómo desglosar (p. ej. «quédate con el punto de "
    "vista» o «con estas medidas»)."
)


@dataclass
class ReferencesTab:
    refresh_all: Callable[[str | None], Awaitable[dict]]
    all_outputs: list[gr.components.Component]
    # Análisis con IA y su previsión en segundos (B-064, `ui.forecast`)
    forecasts: list[tuple[dict[str, Any], float]] = field(default_factory=list)


def status_text(asset: Asset | None) -> str:
    if asset is None:
        return ""
    if asset.sheet is None:
        return "Esta imagen aún no tiene receta: pulsa «Volver a analizar con estas notas»."
    return (
        f"Estado: **{sheet_status(asset)}**. Marca lo que quieres usar de esta imagen; sin nada "
        "marcado, la referencia queda descartada."
    )


def gallery_item(data_dir: Path, project_id: str, asset: Asset) -> tuple[Any, str]:
    path = asset_path(data_dir, project_id, asset)
    image = str(path) if path.is_file() else placeholder(asset.original_name)
    return image, asset_caption(asset)


def build_references_tab(
    client: BackendClient, data_dir: Path, active: gr.BrowserState
) -> ReferencesTab:
    notice = gr.Markdown(NO_PROJECT, visible=False)
    supports_warning = gr.Markdown(visible=False, elem_id="iai-supports-warning")
    with gr.Row(equal_height=False):
        with gr.Column(scale=1):  # 50/50 (B-059)
            gallery = gr.Gallery(
                show_label=False, columns=2, height="auto", object_fit="cover",
                allow_preview=False, buttons=[], elem_classes=["iai-gallery", "iai-cols-2"],
                elem_id="iai-references",
            )  # fmt: skip
            ids = gr.State([])
            with gr.Accordion("Subir una referencia", open=True):
                file = gr.File(
                    label="Imagen (PNG, JPEG o WebP)", file_count="single", file_types=FILE_TYPES,
                    elem_id="iai-reference-file",
                )  # fmt: skip
                upload_notes = gr.Textbox(
                    label="Notas (opcionales)", lines=3, elem_id="iai-reference-upload-notes",
                    placeholder="p. ej. «quédate con el sofá, por módulos» o «con estas medidas»",
                )  # fmt: skip
                gr.Markdown(ANALYSIS_HINT, elem_classes="iai-muted")
                upload_btn = gr.Button(
                    "Subir y analizar", variant="primary", elem_id="iai-reference-upload"
                )
        with gr.Column(scale=1):
            selected = gr.State(None)
            info = gr.Markdown(NO_SELECTION)
            # Ancho de la columna y altura según la imagen (B-061)
            preview = gr.Image(
                show_label=False, interactive=False, buttons=[], visible=False,
                elem_id="iai-reference-preview", elem_classes="iai-viewer",
            )  # fmt: skip
            notes = gr.Textbox(label="Notas", lines=3, elem_id="iai-reference-notes")
            with gr.Row():
                save_notes = gr.Button("Guardar notas", variant="secondary", interactive=False)
                reanalyze = gr.Button(
                    "Volver a analizar con estas notas", variant="secondary", interactive=False,
                    elem_id="iai-reference-reanalyze",
                )  # fmt: skip
            with gr.Accordion("Ficha de la referencia", open=True):
                status = gr.Markdown("")
                tips = gr.HTML(elem_id="iai-sheet-tips")  # oculto: tooltips de las casillas
                with gr.Row():
                    mark_all = gr.Button("Marcar todo", variant="secondary", size="sm")
                    unmark_all = gr.Button("Desmarcar todo", variant="secondary", size="sm")
                group_boxes: dict[str, gr.Checkbox] = {}
                element_boxes: dict[str, gr.CheckboxGroup] = {}
                group_ids: dict[str, gr.State] = {}  # ids de los elementos de cada grupo
                for group, label in RECIPE_GROUPS.items():
                    group_boxes[group] = gr.Checkbox(
                        label=label, visible=False, elem_id=f"iai-sheet-group-{group}"
                    )
                    element_boxes[group] = gr.CheckboxGroup(
                        show_label=False, choices=[], visible=False, elem_id=f"iai-sheet-{group}"
                    )
                    group_ids[group] = gr.State([])
                save_sheet = gr.Button(
                    "Guardar ficha", variant="primary", interactive=False, elem_id="iai-save-sheet"
                )

    groups = list(RECIPE_GROUPS)
    group_outputs = [c for g in groups for c in (group_boxes[g], element_boxes[g], group_ids[g])]
    detail_outputs = [selected, info, preview, notes, save_notes, reanalyze, status, save_sheet,
                      tips, *group_outputs]  # fmt: skip
    panel_outputs = [notice, supports_warning, gallery, ids, *detail_outputs]

    # --- Manejadores ---------------------------------------------------------------------

    def unchanged() -> dict:
        # Gradio interpreta `{}` como un único valor: para no cambiar nada se usa gr.skip().
        return {gallery: gr.skip()}

    def detail(asset: Asset | None, project_id: str | None) -> dict:
        has_sheet = asset is not None and asset.sheet is not None
        updates: dict = {
            selected: str(asset.id) if asset else None,
            info: asset_info_md(asset) if asset else NO_SELECTION,
            preview: gr.update(
                value=str(asset_path(data_dir, project_id, asset)) if asset else None,
                visible=asset is not None,
            ),
            notes: asset.description if asset else "",
            save_notes: gr.update(interactive=asset is not None),
            reanalyze: gr.update(interactive=asset is not None),
            status: status_text(asset),
            save_sheet: gr.update(interactive=has_sheet),
            tips: tooltips_html(sheet_tooltips(asset)),
        }
        for group, (choices, marked) in sheet_groups(asset).items():
            visible = bool(choices)
            updates[group_boxes[group]] = gr.update(
                value=visible and len(marked) == len(choices), visible=visible
            )
            updates[element_boxes[group]] = gr.update(
                choices=choices, value=marked, visible=visible
            )
            updates[group_ids[group]] = [element_id for _, element_id in choices]
        return updates

    async def refresh(active_id: str | None, keep: str | None = None) -> dict:
        if not active_id:
            return {notice: gr.update(visible=True), gallery: [], ids: [],
                    supports_warning: gr.update(visible=False), **detail(None, None)}  # fmt: skip
        try:
            assets = await client.list_assets(active_id, AssetKind.REFERENCIA)
            excluded = excluded_count(await client.get_project(active_id))
        except ApiError as exc:
            gr.Warning(exc.detail)
            return unchanged()
        items = [gallery_item(data_dir, active_id, a) for a in assets]
        asset_ids = [str(a.id) for a in assets]
        current = next((a for a in assets if str(a.id) == keep), None)
        return {
            notice: gr.update(visible=False),
            supports_warning: gr.update(
                value=(
                    f"⚠️ **{excluded} referencia(s) activa(s) no caben** en los bocetos: se envían "
                    f"la imagen base y hasta {MAX_SUPPORTS} apoyos, primero los de perspectiva y "
                    "geometría y después los más antiguos. Las que quedan fuera aparecen con el "
                    "pie en rojo en **Bocetos**; descarta alguna si quieres elegir cuáles."
                ),
                visible=excluded > 0,
            ),
            gallery: gr.update(
                value=items, selected_index=asset_ids.index(keep) if current else None
            ),
            ids: asset_ids,
            **detail(current, active_id),
        }

    async def on_select(evt: gr.SelectData, asset_ids: list[str], active_id: str | None) -> dict:
        if not active_id:
            return unchanged()
        return await refresh(active_id, keep=asset_ids[evt.index])

    async def analyze(active_id: str, asset_id: str, notes_v: str | None) -> bool:
        gr.Info("Analizando la imagen… puede tardar hasta un minuto")
        try:
            body = await client.analyze_reference(active_id, asset_id, notes_v)
        except ApiError as exc:
            gr.Warning(f"No se pudo analizar: {exc.detail}. Pulsa «Volver a analizar».")
            return False
        gr.Info(f"Receta lista · ficha guardada · {euros_up(body['cost_eur'])}")
        return True

    async def on_upload(path: str | None, notes_v: str, active_id: str | None) -> dict:
        """Subir, anotar y analizar: una imagen cada vez (decisión del usuario)."""
        if not active_id:
            gr.Warning("Elige un proyecto antes de subir imágenes")
            return unchanged()
        if not path:
            gr.Warning("Añade una imagen")
            return unchanged()
        source = Path(path)
        try:
            asset = await client.upload_asset(
                active_id, AssetKind.REFERENCIA, source.name,
                await anyio.Path(source).read_bytes(), (notes_v or "").strip(),
            )  # fmt: skip
        except ApiError as exc:
            gr.Warning(f"{source.name}: {exc.detail}")
            return unchanged()
        await analyze(active_id, str(asset.id), None)
        return {**await refresh(active_id, keep=str(asset.id)), file: None, upload_notes: ""}

    async def on_reanalyze(active_id: str | None, asset_id: str | None, notes_v: str) -> dict:
        if not (active_id and asset_id):
            return unchanged()
        await analyze(active_id, asset_id, (notes_v or "").strip())
        return await refresh(active_id, keep=asset_id)

    async def on_save_notes(active_id: str | None, asset_id: str | None, notes_v: str) -> dict:
        if not (active_id and asset_id):
            return unchanged()
        try:
            await client.update_asset_note(active_id, asset_id, (notes_v or "").strip())
        except ApiError as exc:
            gr.Warning(exc.detail)
            return unchanged()
        gr.Info("Notas guardadas (para que cambie la ficha, vuelve a analizar)")
        return await refresh(active_id, keep=asset_id)

    async def on_save_sheet(active_id: str | None, asset_id: str | None, *values: Any) -> dict:
        if not (active_id and asset_id):
            return unchanged()
        chosen = selected_ids(list(values))
        try:
            await client.save_sheet(active_id, asset_id, chosen)
        except ApiError as exc:
            gr.Warning(exc.detail)
            return unchanged()
        gr.Info(
            f"Ficha guardada: {len(chosen)} elemento(s) marcado(s)"
            if chosen
            else "Ficha guardada sin nada marcado: la referencia queda descartada"
        )
        return await refresh(active_id, keep=asset_id)

    # Grupo marcado = todos sus elementos; grupo desmarcado = solo los marcados (B-030). Con
    # `.input` (solo cambios del usuario) los dos niveles se actualizan sin bucles.
    def group_handler(group: str):
        def handler(checked: bool, current: list[str] | None, all_ids: list[str]) -> dict:
            if checked:
                return {element_boxes[group]: all_ids}
            # Desmarcar el grupo vacía sus elementos solo si estaban todos marcados.
            full = set(current or []) == set(all_ids)
            return {element_boxes[group]: [] if full else (current or [])}

        return handler

    def elements_handler(group: str):
        def handler(current: list[str] | None, all_ids: list[str]) -> dict:
            return {group_boxes[group]: bool(all_ids) and set(current or []) == set(all_ids)}

        return handler

    # --- Eventos ---------------------------------------------------------------------------

    gallery.select(on_select, inputs=[ids, active], outputs=panel_outputs)
    uploaded = upload_btn.click(
        on_upload, inputs=[file, upload_notes, active],
        outputs=[*panel_outputs, file, upload_notes],
    )  # fmt: skip
    reanalyzed = reanalyze.click(
        on_reanalyze, inputs=[active, selected, notes], outputs=panel_outputs
    )
    save_notes.click(on_save_notes, inputs=[active, selected, notes], outputs=panel_outputs)
    save_sheet.click(
        on_save_sheet,
        inputs=[active, selected, *(element_boxes[g] for g in groups)],
        outputs=panel_outputs,
    )

    def mark(value: bool):
        """«Marcar todo» / «Desmarcar todo» en el formulario (se guarda con «Guardar ficha»)."""

        def handler(*all_ids: list[str]) -> dict:
            updates: dict = {}
            for group, ids_of_group in zip(groups, all_ids, strict=True):
                updates[element_boxes[group]] = list(ids_of_group) if value else []
                updates[group_boxes[group]] = value and bool(ids_of_group)
            return updates

        return handler

    marks = [c for g in groups for c in (element_boxes[g], group_boxes[g])]
    state_inputs = [group_ids[g] for g in groups]
    mark_all.click(mark(True), inputs=state_inputs, outputs=marks)
    unmark_all.click(mark(False), inputs=state_inputs, outputs=marks)
    for group in groups:
        group_boxes[group].input(
            group_handler(group),
            inputs=[group_boxes[group], element_boxes[group], group_ids[group]],
            outputs=element_boxes[group],
        )
        element_boxes[group].input(
            elements_handler(group),
            inputs=[element_boxes[group], group_ids[group]],
            outputs=group_boxes[group],
        )

    async def refresh_all(active_id: str | None) -> dict:
        return await refresh(active_id)

    analysis = FORECAST_S["analisis"]
    return ReferencesTab(refresh_all, panel_outputs, [(uploaded, analysis), (reanalyzed, analysis)])
