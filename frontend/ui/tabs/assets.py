"""Pestaña Assets: las imágenes del proyecto activo, todas referencias desde la v2 (B-028).

Subir (vía API), ver, anotar y borrar (papelera); indexar con el CONTEXT_MANAGER (botón
manual, con coste en modo azure) y validar la ficha.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio
import gradio as gr

from shared.models import Asset, AssetKind
from ui.api_client import ApiError, BackendClient
from ui.covers import asset_path, placeholder
from ui.views import (
    CATEGORY_CHOICES,
    DIMENSION_SOURCE_CHOICES,
    analysis_form_values,
    analysis_status,
    asset_caption,
    asset_info_md,
    parse_analysis_form,
)

FILE_TYPES = [".png", ".jpg", ".jpeg", ".webp"]
NO_PROJECT = "### Ningún proyecto activo\nElige o crea un proyecto en la pestaña **Proyectos**."
NO_SELECTION = "Selecciona una imagen de la galería para ver su detalle."
INDEX_HINT = (
    "Llama a la IA (CONTEXT_MANAGER) solo para las referencias **sin indexar**. "
    "En modo Azure ≈ 0,0004 € por referencia; en simulación, sin coste."
)

Handler = Callable[..., Awaitable[dict]]


@dataclass
class AssetsTab:
    refresh_all: Callable[[str | None], Awaitable[dict]]
    all_outputs: list[gr.components.Component]


def gallery_item(data_dir: Path, project_id: str, asset: Asset) -> tuple[Any, str]:
    path = asset_path(data_dir, project_id, asset)
    image = str(path) if path.is_file() else placeholder(asset.original_name)
    return image, asset_caption(asset)


def build_assets_tab(client: BackendClient, data_dir: Path, active: gr.BrowserState) -> AssetsTab:
    heading = gr.Markdown(NO_PROJECT)
    kind, slug = AssetKind.REFERENCIA, "referencia"
    with gr.Row(equal_height=False):
        with gr.Column(scale=3):
            gallery = gr.Gallery(
                show_label=False, columns=3, height="auto", object_fit="cover",
                allow_preview=False, buttons=[], elem_classes="iai-gallery",
            )  # fmt: skip
            ids = gr.State([])
            with gr.Row(equal_height=True):
                index_btn = gr.Button(
                    "Indexar referencias pendientes", variant="primary", scale=0,
                    min_width=280, elem_id="iai-index-references",
                )  # fmt: skip
                gr.Markdown(INDEX_HINT)
            with gr.Accordion("Subir imágenes", open=True):
                files = gr.File(
                    label="PNG, JPEG o WebP", file_count="multiple", file_types=FILE_TYPES,
                    elem_id=f"iai-{slug}-files",
                )  # fmt: skip
                upload_note = gr.Textbox(
                    label="Nota para las imágenes subidas (opcional)",
                    placeholder="p. ej. medidas, origen, qué aporta al diseño",
                )
                upload_btn = gr.Button("Subir", variant="secondary", elem_id=f"iai-{slug}-upload")
        with gr.Column(scale=2):
            selected = gr.State(None)
            info = gr.Markdown(NO_SELECTION)
            preview = gr.Image(
                show_label=False, interactive=False, height=320, buttons=[], visible=False
            )
            note = gr.Textbox(label="Nota", lines=3, elem_id=f"iai-{slug}-note")
            with gr.Row():
                save_note = gr.Button("Guardar nota", variant="secondary", interactive=False)
                delete = gr.Button("Mover a la papelera", variant="secondary", interactive=False)
            with gr.Row():
                confirm = gr.Button(
                    "Confirmar: mover a la papelera", visible=False, elem_classes="iai-danger"
                )
                cancel = gr.Button("Cancelar", visible=False, variant="secondary")
            with gr.Accordion("Ficha de la referencia", open=True):
                status = gr.Markdown("")
                with gr.Row():
                    category = gr.Dropdown(CATEGORY_CHOICES, label="Categoría")
                    item_name = gr.Textbox(label="Objeto", elem_id="iai-ficha-item")
                with gr.Row():
                    brand = gr.Textbox(label="Marca")
                    product = gr.Textbox(label="Producto")
                style_tags = gr.Textbox(label="Estilos (separados por comas)")
                colors = gr.Textbox(label="Colores (separados por comas)")
                materials = gr.Textbox(
                    label="Materiales (separados por comas)", elem_id="iai-ficha-materials"
                )
                with gr.Row():
                    width = gr.Number(label="Ancho (cm)", minimum=0)
                    depth = gr.Number(label="Fondo (cm)", minimum=0)
                    height = gr.Number(label="Alto (cm)", minimum=0)
                source = gr.Dropdown(DIMENSION_SOURCE_CHOICES, label="Origen de las medidas")
                summary = gr.Textbox(label="Resumen", lines=2)
                relevance = gr.Textbox(label="Qué aporta al diseño", lines=2)
                validate = gr.Button(
                    "Validar ficha", variant="primary", interactive=False,
                    elem_id="iai-validate-ficha",
                )  # fmt: skip
            ficha = [category, item_name, brand, product, style_tags, colors, materials,
                     width, depth, height, source, summary, relevance]  # fmt: skip

    detail_outputs = [selected, info, preview, note, save_note, delete, status, *ficha, validate]

    # --- Manejadores ---------------------------------------------------------------------

    def unchanged() -> dict:
        # Gradio interpreta `{}` como un único valor: para no cambiar nada se usa gr.skip().
        return {gallery: gr.skip()}

    def detail(asset: Asset | None, project_id: str | None) -> dict:
        updates: dict = {
            selected: str(asset.id) if asset else None,
            info: asset_info_md(asset) if asset else NO_SELECTION,
            preview: gr.update(
                value=str(asset_path(data_dir, project_id, asset)) if asset else None,
                visible=asset is not None,
            ),
            note: asset.description if asset else "",
            save_note: gr.update(interactive=asset is not None),
            delete: gr.update(interactive=asset is not None),
        }
        values = analysis_form_values(asset) if asset else [None] * len(ficha)
        updates |= {
            status: f"Estado de la ficha: **{analysis_status(asset)}**" if asset else "",
            **dict(zip(ficha, values, strict=True)),
            validate: gr.update(interactive=asset is not None),
        }
        return updates

    async def refresh(active_id: str | None, keep: str | None = None) -> dict:
        if not active_id:
            return {gallery: [], ids: [], **detail(None, None)}
        try:
            assets = await client.list_assets(active_id, kind)
        except ApiError as exc:
            gr.Warning(exc.detail)
            return unchanged()
        items = [gallery_item(data_dir, active_id, a) for a in assets]
        asset_ids = [str(a.id) for a in assets]
        current = next((a for a in assets if str(a.id) == keep), None)
        return {
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

    async def on_upload(paths: list[str] | None, note_v: str, active_id: str | None) -> dict:
        if not active_id:
            gr.Warning("Elige un proyecto antes de subir imágenes")
            return unchanged()
        if not paths:
            gr.Warning("Añade al menos una imagen")
            return unchanged()
        uploaded = 0
        for raw in paths:
            path = Path(raw)
            try:
                await client.upload_asset(
                    active_id,
                    kind,
                    path.name,
                    await anyio.Path(path).read_bytes(),
                    (note_v or "").strip(),
                )
                uploaded += 1
            except ApiError as exc:
                gr.Warning(f"{path.name}: {exc.detail}")
        if uploaded:
            gr.Info(f"{uploaded} imagen(es) subida(s)")
        return {**await refresh(active_id), files: None, upload_note: ""}

    async def on_save_note(active_id: str | None, asset_id: str | None, note_v: str) -> dict:
        if not (active_id and asset_id):
            return unchanged()
        try:
            await client.update_asset_note(active_id, asset_id, (note_v or "").strip())
        except ApiError as exc:
            gr.Warning(exc.detail)
            return unchanged()
        gr.Info("Nota guardada")
        return await refresh(active_id, keep=asset_id)

    def ask_delete() -> dict:
        return {confirm: gr.update(visible=True), cancel: gr.update(visible=True)}

    def hide_delete() -> dict:
        return {confirm: gr.update(visible=False), cancel: gr.update(visible=False)}

    async def on_confirm_delete(active_id: str | None, asset_id: str | None) -> dict:
        if active_id and asset_id:
            try:
                await client.delete_asset(active_id, asset_id)
                gr.Info("Imagen movida a la papelera (recuperable)")
            except ApiError as exc:
                gr.Warning(exc.detail)
        return {**await refresh(active_id), **hide_delete()}

    panel_outputs = [gallery, ids, *detail_outputs]
    gallery.select(on_select, inputs=[ids, active], outputs=panel_outputs)
    upload_btn.click(
        on_upload, inputs=[files, upload_note, active], outputs=[*panel_outputs, files, upload_note]
    )
    save_note.click(on_save_note, inputs=[active, selected, note], outputs=panel_outputs)
    delete.click(ask_delete, outputs=[confirm, cancel])
    cancel.click(hide_delete, outputs=[confirm, cancel])
    confirm.click(
        on_confirm_delete, inputs=[active, selected], outputs=[*panel_outputs, confirm, cancel]
    )

    async def on_index(active_id: str | None, asset_id: str | None) -> dict:
        if not active_id:
            return unchanged()
        try:
            result = await client.index_references(active_id)
        except ApiError as exc:
            gr.Warning(exc.detail)
            return unchanged()
        failed = result.get("failed", [])
        for failure in failed:
            gr.Warning(f"No se pudo indexar: {failure['error']}")
        gr.Info(
            f"Indexadas: {len(result['indexed'])} · ya indexadas: {len(result['skipped'])}"
            f" · coste: {result['cost_eur']:.4f} €"
        )
        return await refresh(active_id, keep=asset_id)

    async def on_validate(active_id: str | None, asset_id: str | None, *values: Any) -> dict:
        if not (active_id and asset_id):
            return unchanged()
        try:
            analysis = parse_analysis_form(list(values))
            await client.validate_analysis(active_id, asset_id, analysis)
        except (ApiError, ValueError) as exc:
            gr.Warning(getattr(exc, "detail", str(exc)))
            return unchanged()
        gr.Info("Ficha validada")
        return await refresh(active_id, keep=asset_id)

    index_btn.click(on_index, inputs=[active, selected], outputs=panel_outputs)
    validate.click(on_validate, inputs=[active, selected, *ficha], outputs=panel_outputs)

    async def refresh_all(active_id: str | None) -> dict:
        updates: dict = {heading: NO_PROJECT}
        if active_id:
            try:
                project = await client.get_project(active_id)
                updates[heading] = f"### Assets de «{project.name}»"
            except ApiError:
                active_id = None
        return updates | await refresh(active_id)

    return AssetsTab(refresh_all, [heading, *panel_outputs])
