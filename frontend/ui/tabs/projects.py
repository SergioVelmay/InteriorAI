"""Pestaña Proyectos: galería con portadas, ficha editable, creación y borrado (papelera)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gradio as gr

from shared.models import ProjectCreate, ProjectMetadata, SpaceType
from ui.api_client import ApiError, BackendClient, Health
from ui.covers import cover_image
from ui.views import form_values, gallery_caption, header_html, parse_form, project_summary_md

SPACE_CHOICES = [(t.label, t.value) for t in SpaceType]
EMPTY_SUMMARY = (
    "### Ningún proyecto seleccionado\nElige una tarjeta de la galería o crea un proyecto nuevo."
)


@dataclass
class ProjectsTab:
    gallery: gr.Gallery
    summary: gr.Markdown
    fields: list[gr.components.Component]
    refresh_all: Callable[[str | None], Awaitable[dict]]  # recarga galería, cabecera y ficha
    all_outputs: list[gr.components.Component]  # salidas de `refresh_all`


async def load_projects(
    client: BackendClient, data_dir: Path
) -> tuple[list[ProjectMetadata], list[tuple[Any, str]], list[str]]:
    summaries = await client.list_projects()
    projects = list(await asyncio.gather(*(client.get_project(s.id) for s in summaries)))
    items = [(cover_image(p, data_dir), gallery_caption(p)) for p in projects]
    return projects, items, [str(p.id) for p in projects]


async def safe_health(client: BackendClient) -> Health | None:
    try:
        return await client.health()
    except ApiError:
        return None


def build_projects_tab(
    client: BackendClient,
    data_dir: Path,
    active: gr.BrowserState,
    header: gr.HTML,
) -> ProjectsTab:
    with gr.Row(equal_height=False):
        with gr.Column(scale=3):
            gallery = gr.Gallery(
                label="Proyectos",
                show_label=False,
                columns=3,
                height="auto",
                object_fit="cover",
                allow_preview=False,
                buttons=[],  # galería de selección: sin descargar ni pantalla completa
                elem_classes="iai-gallery",
            )
            ids = gr.State([])
            refresh = gr.Button("Actualizar", variant="secondary", size="sm")
            with gr.Accordion("Nuevo proyecto", open=False):
                new_name = gr.Textbox(
                    label="Nombre", placeholder="Salón-cocina-comedor", elem_id="iai-new-name"
                )
                new_type = gr.Dropdown(SPACE_CHOICES, label="Tipo de espacio", value="salon")
                new_description = gr.Textbox(label="Descripción", lines=2)
                new_notes = gr.Textbox(label="Notas de diseño", lines=4)
                create = gr.Button("Crear proyecto", variant="primary")
        with gr.Column(scale=2):
            summary = gr.Markdown(EMPTY_SUMMARY)
            with gr.Group():
                name = gr.Textbox(label="Nombre", elem_id="iai-project-name")
                space_type = gr.Dropdown(SPACE_CHOICES, label="Tipo de espacio")
                description = gr.Textbox(
                    label="Descripción", lines=2, elem_id="iai-project-description"
                )
                design_notes = gr.Textbox(label="Notas de diseño", lines=6)
                with gr.Row():
                    width = gr.Number(label="Ancho (m)", minimum=0)
                    length = gr.Number(label="Largo (m)", minimum=0)
                    height = gr.Number(label="Alto (m)", minimum=0)
                with gr.Row():
                    style = gr.Textbox(label="Estilo")
                    budget = gr.Number(label="Presupuesto (€)", minimum=0)
            with gr.Row():
                save = gr.Button("Guardar cambios", variant="primary", interactive=False)
                delete = gr.Button("Mover a la papelera", variant="secondary", interactive=False)
            with gr.Row():
                confirm_delete = gr.Button(
                    "Confirmar: mover a la papelera", visible=False, elem_classes="iai-danger"
                )
                cancel_delete = gr.Button("Cancelar", visible=False, variant="secondary")

    fields = [name, space_type, description, design_notes, width, length, height, style, budget]
    detail_outputs = [summary, *fields, save, delete]

    # --- Manejadores ---------------------------------------------------------------------

    def detail(project: ProjectMetadata | None, costs: dict | None) -> dict:
        if project is None:
            return {
                summary: EMPTY_SUMMARY,
                **dict.fromkeys(fields, None),
                save: gr.update(interactive=False),
                delete: gr.update(interactive=False),
            }
        return {
            summary: project_summary_md(project, costs),
            **dict(zip(fields, form_values(project), strict=True)),
            save: gr.update(interactive=True),
            delete: gr.update(interactive=True),
        }

    async def refresh_all(active_id: str | None) -> dict:
        health = await safe_health(client)
        try:
            projects, items, project_ids = await load_projects(client, data_dir)
        except ApiError as exc:
            gr.Warning(exc.detail)
            return {header: header_html(health, None)}
        current = next((p for p in projects if str(p.id) == active_id), None)
        costs = await client.project_costs(current.id) if current else None
        return {
            header: header_html(health, current),
            gallery: gr.update(
                value=items,
                selected_index=project_ids.index(active_id) if current else None,
            ),
            ids: project_ids,
            active: str(current.id) if current else None,
            **detail(current, costs),
        }

    async def on_select(evt: gr.SelectData, project_ids: list[str]) -> dict:
        project_id = project_ids[evt.index]
        try:
            project = await client.get_project(project_id)
            costs = await client.project_costs(project_id)
        except ApiError as exc:
            gr.Warning(exc.detail)
            return {}
        return {
            active: project_id,
            header: header_html(await safe_health(client), project),
            **detail(project, costs),
        }

    async def on_create(name_v: str, type_v: str, description_v: str, notes_v: str) -> dict:
        if not (name_v or "").strip():
            gr.Warning("Ponle un nombre al proyecto")
            return {}
        try:
            data = ProjectCreate(
                name=name_v, space_type=type_v, description=description_v or "",
                design_notes=notes_v or "",
            )  # fmt: skip
            project = await client.create_project(data)
        except (ApiError, ValueError) as exc:
            gr.Warning(getattr(exc, "detail", str(exc)))
            return {}
        gr.Info(f"Proyecto «{project.name}» creado")
        return {
            **await refresh_all(str(project.id)),
            new_name: "",
            new_description: "",
            new_notes: "",
        }

    async def on_save(active_id: str | None, *values: Any) -> dict:
        if not active_id:
            return {}
        try:
            project = await client.update_project(active_id, parse_form(list(values)))
        except (ApiError, ValueError) as exc:
            gr.Warning(getattr(exc, "detail", str(exc)))
            return {}
        gr.Info(f"Cambios guardados en «{project.name}»")
        return await refresh_all(active_id)

    def ask_delete() -> dict:
        return {confirm_delete: gr.update(visible=True), cancel_delete: gr.update(visible=True)}

    def hide_delete() -> dict:
        return {confirm_delete: gr.update(visible=False), cancel_delete: gr.update(visible=False)}

    async def on_confirm_delete(active_id: str | None) -> dict:
        if not active_id:
            return hide_delete()
        try:
            await client.delete_project(active_id)
        except ApiError as exc:
            gr.Warning(exc.detail)
            return hide_delete()
        gr.Info("Proyecto movido a la papelera (recuperable desde data/.papelera)")
        return {**await refresh_all(None), **hide_delete()}

    # --- Eventos ---------------------------------------------------------------------------

    all_outputs = [header, gallery, ids, active, *detail_outputs]
    create_outputs = [*all_outputs, new_name, new_description, new_notes]
    delete_outputs = [*all_outputs, confirm_delete, cancel_delete]

    refresh.click(refresh_all, inputs=active, outputs=all_outputs)
    gallery.select(on_select, inputs=ids, outputs=[active, header, *detail_outputs])
    create.click(
        on_create, inputs=[new_name, new_type, new_description, new_notes], outputs=create_outputs
    )
    save.click(on_save, inputs=[active, *fields], outputs=all_outputs)
    delete.click(ask_delete, outputs=[confirm_delete, cancel_delete])
    cancel_delete.click(hide_delete, outputs=[confirm_delete, cancel_delete])
    confirm_delete.click(on_confirm_delete, inputs=active, outputs=delete_outputs)

    return ProjectsTab(gallery, summary, fields, refresh_all, all_outputs)
