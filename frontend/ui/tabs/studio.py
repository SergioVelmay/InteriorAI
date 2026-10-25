"""Pestaña Estudio: tres pestañas, una por etapa (B-035), que se desbloquean en orden (B-043).

① Bocetos (Paso 22): las referencias activas → generar (prompt automático, sin brief) → elegir
uno. ② Composición y ③ Render Final: los controles de la v1, provisionales hasta los Pasos 23 y
24. En cada pestaña, la imagen seleccionada en grande con lo que entendió la IA, el prompt y lo
enviado al modelo (B-047); la confirmación de coste, junto al botón que la pide (B-049).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gradio as gr
from PIL import Image

from shared.models import ProjectMetadata, RenderStage, RenderStatus
from ui.api_client import ApiError, BackendClient
from ui.cost_views import alert_lines, chain_cost_md
from ui.covers import asset_path, placeholder
from ui.studio_views import (
    COST_AUDIT,
    COST_INPAINT,
    COST_PER_IMAGE,
    COST_PROMPT,
    DRAFT_SIZES,
    QUALITIES,
    active_references,
    audit_markdown,
    cost_hint,
    default_textures,
    draft_cost,
    draft_inputs,
    editor_mask,
    euros,
    inpaint_hint,
    needs_confirmation,
    reference_choices,
    reference_summary,
    render_caption,
    render_detail_md,
    render_inputs,
    render_title_md,
    renders_of,
    selected_render,
)

NO_PROJECT = "Ningún proyecto activo: elige o crea uno en la pestaña **Proyectos**."
NO_REFERENCES = (
    "⚠️ No hay referencias activas: marca en **Referencias** lo que quieres usar de cada imagen "
    "para poder generar bocetos."
)
STAGES = (RenderStage.DRAFT, RenderStage.COMPOSITION, RenderStage.FINAL)


@dataclass
class StudioTab:
    refresh_all: Callable[[str | None], Awaitable[dict]]
    all_outputs: list[gr.components.Component]
    show_render: Callable[[str | None, str | None], Awaitable[dict]]  # abre una imagen


@dataclass
class Panel:
    """Lo común de las tres pestañas: generar (con su confirmación), miniaturas y vista."""

    stage: RenderStage
    generate: gr.Button
    cost: gr.Markdown
    confirm_box: gr.Column
    confirm_md: gr.Markdown
    confirm_btn: gr.Button
    cancel_btn: gr.Button
    pending: gr.State
    gallery: gr.Gallery
    ids: gr.State
    viewer: gr.Image
    title: gr.Markdown
    select_btn: gr.Button
    more_md: gr.Markdown
    inputs: gr.Gallery
    shown: gr.State

    def components(self) -> list[gr.components.Component]:
        return [self.generate, self.cost, self.confirm_box, self.confirm_md, self.pending,
                self.gallery, self.ids, self.viewer, self.title, self.select_btn, self.more_md,
                self.inputs, self.shown]  # fmt: skip


def _generate_area(label: str, slug: str) -> dict[str, Any]:
    with gr.Row(equal_height=True):
        generate = gr.Button(label, variant="primary", elem_id=f"iai-gen-{slug}")
        cost = gr.Markdown(elem_classes="iai-muted")
    # Confirmación justo debajo del botón que la pide (B-049).
    with gr.Column(visible=False, elem_id=f"iai-confirm-{slug}") as confirm_box:
        confirm_md = gr.Markdown()
        with gr.Row():
            confirm_btn = gr.Button("Confirmar (con coste)", elem_classes="iai-danger")
            cancel_btn = gr.Button("Cancelar", variant="secondary")
    return {"generate": generate, "cost": cost, "confirm_box": confirm_box,
            "confirm_md": confirm_md, "confirm_btn": confirm_btn, "cancel_btn": cancel_btn,
            "pending": gr.State(None)}  # fmt: skip


def _thumbnails(slug: str) -> dict[str, Any]:
    gallery = gr.Gallery(
        show_label=False, columns=2, height="auto", object_fit="cover", allow_preview=False,
        buttons=[], elem_classes="iai-gallery", elem_id=f"iai-{slug}",
    )  # fmt: skip
    return {"gallery": gallery, "ids": gr.State([])}


def _viewer(slug: str) -> dict[str, Any]:
    viewer = gr.Image(
        show_label=False, interactive=False, buttons=["download", "fullscreen"],
        elem_id=f"iai-viewer-{slug}",
    )  # fmt: skip
    title = gr.Markdown()
    select_btn = gr.Button("Seleccionar", variant="primary", elem_id=f"iai-select-{slug}")
    with gr.Accordion("Ver más: lo que entendió la IA, el prompt y lo enviado", open=False):
        more_md = gr.Markdown(elem_id=f"iai-more-{slug}")
        inputs = gr.Gallery(
            label="Enviado al modelo", columns=4, height="auto", object_fit="contain",
            allow_preview=False, buttons=[], elem_classes=["iai-gallery", "iai-small"],
            elem_id=f"iai-inputs-{slug}",
        )  # fmt: skip
    return {"viewer": viewer, "title": title, "select_btn": select_btn, "more_md": more_md,
            "inputs": inputs}  # fmt: skip


def build_studio_tab(client: BackendClient, data_dir: Path, active: gr.BrowserState) -> StudioTab:
    mode = gr.State(None)
    selected_draft = gr.State(None)  # id del boceto seleccionado (entrada de la composición)
    selected_composition = gr.State(None)  # id de la composición seleccionada
    notice = gr.Markdown(NO_PROJECT, visible=False)
    panels: dict[RenderStage, Panel] = {}
    shown_images: dict[str, Any] = {}  # imagen de cada composición mostrada (para el editor)

    with gr.Tabs(selected="bocetos"):
        # ① Bocetos -------------------------------------------------------------------------
        with gr.Tab("Bocetos", id="bocetos"):
            refs_md = gr.Markdown(elem_id="iai-active-references")
            refs = gr.Gallery(
                show_label=False, columns=6, height="auto", object_fit="cover",
                allow_preview=False, buttons=[], elem_classes="iai-gallery",
                elem_id="iai-studio-references",
            )  # fmt: skip
            with gr.Row(equal_height=False):
                with gr.Column(scale=1):
                    with gr.Row():
                        draft_quality = gr.Radio(QUALITIES, value="medium", label="Calidad")
                        draft_size = gr.Radio(DRAFT_SIZES, value="1536x1024", label="Formato")
                    draft_n = gr.Slider(1, 8, value=4, step=1, label="Variantes")
                    draft_extra = gr.Textbox(
                        label="Indicaciones (opcionales)", lines=2,
                        placeholder="p. ej. «más cálido, tarde de otoño, alfombra de yute»",
                        elem_id="iai-draft-indications",
                    )  # fmt: skip
                    draft_gen = _generate_area("Generar bocetos", "drafts")
                    draft_thumbs = _thumbnails("drafts")
                with gr.Column(scale=1):
                    draft_view = _viewer("drafts")
            panels[RenderStage.DRAFT] = Panel(
                RenderStage.DRAFT, **draft_gen, **draft_thumbs, **draft_view, shown=gr.State(None)
            )

        # ② Composición (provisional hasta el Paso 23) -----------------------------------------
        with gr.Tab("Composición", id="composicion", interactive=False) as composition_tab:
            with gr.Row(equal_height=False):
                with gr.Column(scale=1):
                    comp_source = gr.Markdown()
                    comp_quality = gr.Radio(QUALITIES, value="medium", label="Calidad")
                    comp_extra = gr.Textbox(label="Indicaciones (opcionales)", lines=2)
                    comp_gen = _generate_area("Generar composición", "compositions")
                    comp_thumbs = _thumbnails("compositions")
                with gr.Column(scale=1):
                    comp_view = _viewer("compositions")
                    with gr.Row(equal_height=True):
                        comp_audit = gr.Button(
                            "Auditar", variant="secondary", elem_id="iai-audit-composition"
                        )
                        comp_audit_cost = gr.Markdown(elem_classes="iai-muted")
                    comp_audit_md = gr.Markdown()
            panels[RenderStage.COMPOSITION] = Panel(
                RenderStage.COMPOSITION, **comp_gen, **comp_thumbs, **comp_view,
                shown=gr.State(None),
            )  # fmt: skip
            # Contador para volver a montar el editor al hacerse visible: montado en una pestaña
            # o un desplegable ocultos, el lienzo exporta el fondo truncado (Gradio 6).
            editor_nonce = gr.State(0)
            with gr.Accordion("Retocar zona de la composición", open=False) as retouch_box:
                gr.Markdown(
                    "Pinta la zona que quieres cambiar y describe el cambio. El modelo edita esa "
                    "zona con la máscara y devuelve la imagen completa: el retoque es una "
                    "composición nueva que puedes seleccionar; la original no cambia."
                )
                comp_shown = panels[RenderStage.COMPOSITION].shown

                # Un editor nuevo por imagen: cambiar por código el valor de un ImageEditor ya
                # montado lo deja sin la capa de trazos (Gradio 6).
                @gr.render(
                    inputs=[comp_shown, mode, editor_nonce], triggers=[editor_nonce.change],
                    concurrency_limit=1,
                )  # fmt: skip
                def inpaint_area(
                    render_id: str | None, current_mode: str | None, nonce: int
                ) -> None:
                    image = shown_images.get(render_id or "")
                    if image is None:
                        gr.Markdown("_Elige una composición._")
                        return
                    if isinstance(image, str):
                        # Ya cargada: con una ruta, el editor puede reenviar el fondo truncado.
                        with Image.open(image) as opened:
                            image = opened.convert("RGB")
                    editor = gr.ImageEditor(
                        value={"background": image, "layers": [], "composite": None},
                        type="pil", format="png", sources=(), transforms=(), layers=False,
                        brush=gr.Brush(colors=[("#ef4444", 0.6)], color_mode="fixed",
                                       default_size=40),
                        eraser=gr.Eraser(default_size=40), show_label=False, height=560,
                        interactive=True, key=f"iai-editor-{render_id}-{nonce}",
                        elem_id="iai-inpaint-editor",
                    )  # fmt: skip
                    instruction = gr.Textbox(
                        label="Cambio en la zona pintada", lines=2,
                        key=f"iai-instruction-{render_id}-{nonce}",
                        elem_id="iai-inpaint-instruction",
                    )  # fmt: skip
                    with gr.Row(equal_height=True):
                        button = gr.Button("Retocar zona", variant="primary", elem_id="iai-inpaint")
                        gr.Markdown(inpaint_hint(RenderStage.COMPOSITION, current_mode) or "")
                    button.click(on_inpaint, inputs=[*common, editor, instruction], outputs=outputs)

        # ③ Render Final (provisional hasta el Paso 24) ------------------------------------------
        with gr.Tab("Render Final", id="render_final", interactive=False) as final_tab:
            with gr.Row(equal_height=False):
                with gr.Column(scale=1):
                    final_source = gr.Markdown()
                    textures = gr.CheckboxGroup(label="Referencias de textura y color", choices=[])
                    final_extra = gr.Textbox(label="Indicaciones (opcionales)", lines=2)
                    final_gen = _generate_area("Generar render final", "finals")
                    final_thumbs = _thumbnails("finals")
                with gr.Column(scale=1):
                    final_view = _viewer("finals")
                    with gr.Row(equal_height=True):
                        final_audit = gr.Button(
                            "Auditar", variant="secondary", elem_id="iai-audit-final"
                        )
                        final_audit_cost = gr.Markdown(elem_classes="iai-muted")
                    final_audit_md = gr.Markdown()
            panels[RenderStage.FINAL] = Panel(
                RenderStage.FINAL, **final_gen, **final_thumbs, **final_view, shown=gr.State(None)
            )

    shown_states = [panels[s].shown for s in STAGES]
    common = [active, mode, *shown_states]

    # --- Vista ------------------------------------------------------------------------------

    def image_of(project: ProjectMetadata, render_id: str) -> Any:
        asset = next((a for a in project.assets if str(a.id) == render_id), None)
        if asset is None:
            return placeholder("?")
        path = asset_path(data_dir, project.id, asset)
        return str(path) if path.is_file() else placeholder(asset.original_name)

    def empty_view() -> dict:
        updates: dict = {notice: gr.update(visible=True), mode: None, refs: [], refs_md: "",
                         selected_draft: None, selected_composition: None,
                         composition_tab: gr.update(interactive=False),
                         final_tab: gr.update(interactive=False)}  # fmt: skip
        for panel in panels.values():
            updates |= {panel.gallery: [], panel.ids: [], panel.viewer: None, panel.title: "",
                        panel.more_md: "", panel.inputs: [], panel.shown: None,
                        panel.generate: gr.update(interactive=False),
                        panel.select_btn: gr.update(interactive=False)}  # fmt: skip
        return updates

    async def panel_updates(
        project: ProjectMetadata, stage: RenderStage, render_id: str | None, current_mode: str
    ) -> tuple[dict, Any]:
        panel = panels[stage]
        renders = {str(r.id): r for r in project.renders if r.stage is stage}
        items = renders_of(project, stage)
        if render_id not in renders:
            chosen = selected_render(project, stage) or (items[0] if items else None)
            render_id = str(chosen.id) if chosen else None
        render = renders.get(render_id or "")
        chain = ""
        if render is not None:
            try:  # lo que ha costado llegar a esta imagen
                chain = "\n\n" + chain_cost_md(await client.render_cost(project.id, render.id))
            except ApiError:
                chain = ""
        image = image_of(project, render_id) if render else None
        if render is not None and stage is RenderStage.COMPOSITION:
            shown_images[str(render.id)] = image
        is_selected = render is not None and render.status is RenderStatus.SELECTED
        return {
            panel.shown: render_id,
            panel.gallery: gr.update(
                value=[(image_of(project, str(r.id)), render_caption(r)) for r in items],
                selected_index=next(
                    (i for i, r in enumerate(items) if str(r.id) == render_id), None
                ),
            ),
            panel.ids: [str(r.id) for r in items],
            panel.viewer: image,
            panel.title: render_title_md(render),
            panel.select_btn: gr.update(
                interactive=render is not None and not is_selected,
                value="Seleccionada ●" if is_selected else "Seleccionar",
            ),
            panel.more_md: render_detail_md(project, render) + chain,
            panel.inputs: render_inputs(project, render, data_dir),
        }, render

    async def view(active_id: str | None, *shown: str | None) -> dict:
        if not active_id:
            return empty_view()
        try:
            project = await client.get_project(active_id)
            health = await client.health()
        except ApiError as exc:
            gr.Warning(exc.detail)
            return empty_view()
        current_mode = health.mode
        updates: dict = {notice: gr.update(visible=False), mode: current_mode}

        # Referencias activas (cabecera de Bocetos).
        actives = active_references(project)
        updates[refs] = [(str(asset_path(data_dir, project.id, a)), reference_summary(a))
                         for a in actives]  # fmt: skip
        updates[refs_md] = (
            f"**Referencias activas ({len(actives)})** · se usa lo marcado en cada ficha; "
            "cuantas más selecciones, más restringido el resultado."
            if actives
            else NO_REFERENCES
        )

        shown_renders = {}
        for stage, render_id in zip(STAGES, shown, strict=True):
            stage_updates, shown_renders[stage] = await panel_updates(
                project, stage, render_id, current_mode
            )
            updates |= stage_updates

        draft = selected_render(project, RenderStage.DRAFT)
        composition = selected_render(project, RenderStage.COMPOSITION)
        comp_render, final_render = (shown_renders[RenderStage.COMPOSITION],
                                     shown_renders[RenderStage.FINAL])  # fmt: skip
        updates |= {
            selected_draft: str(draft.id) if draft else None,
            selected_composition: str(composition.id) if composition else None,
            composition_tab: gr.update(interactive=draft is not None),
            final_tab: gr.update(interactive=composition is not None),
            panels[RenderStage.DRAFT].generate: gr.update(interactive=bool(actives)),
            panels[RenderStage.COMPOSITION].generate: gr.update(interactive=draft is not None),
            panels[RenderStage.FINAL].generate: gr.update(interactive=composition is not None),
            comp_source: (
                f"**Boceto de partida:** el seleccionado (`{draft.id.hex[:8]}`)"
                if draft else "Selecciona un boceto para componer."
            ),
            final_source: (
                f"**Composición de partida:** la seleccionada (`{composition.id.hex[:8]}`)"
                if composition else "Selecciona una composición para el render final."
            ),
            textures: gr.update(
                choices=reference_choices(project), value=default_textures(project)
            ),
            comp_audit_md: audit_markdown(
                comp_render.audits[-1] if comp_render and comp_render.audits else None
            ),
            final_audit_md: audit_markdown(
                final_render.audits[-1] if final_render and final_render.audits else None
            ),
            comp_audit: gr.update(interactive=comp_render is not None),
            final_audit: gr.update(interactive=final_render is not None),
            comp_audit_cost: cost_hint(COST_AUDIT, current_mode),
            final_audit_cost: cost_hint(COST_AUDIT, current_mode),
            panels[RenderStage.DRAFT].cost: cost_hint(
                draft_cost(4, "medium", draft_inputs(project)), current_mode
            ) + " (4 en calidad media)",
            panels[RenderStage.COMPOSITION].cost: cost_hint(
                COST_PER_IMAGE[RenderStage.COMPOSITION] + COST_PROMPT, current_mode
            ),
            panels[RenderStage.FINAL].cost: cost_hint(
                COST_PER_IMAGE[RenderStage.FINAL] + COST_PROMPT, current_mode
            ),
        }  # fmt: skip
        return updates

    # --- Acciones de IA (confirmación junto al botón en Azure, B-049) ---------------------------

    def estimate(action: dict[str, Any], project_inputs: int) -> float:
        kind = action["kind"]
        if kind == "audit":
            return COST_AUDIT
        if kind == "inpaint":
            return COST_INPAINT[RenderStage.COMPOSITION]
        if kind == RenderStage.DRAFT.value:
            body = action["body"]
            return draft_cost(body["n"], body["quality"], project_inputs)
        return COST_PER_IMAGE[RenderStage(kind)] + COST_PROMPT

    def describe(action: dict[str, Any]) -> str:
        kind = action["kind"]
        if kind == RenderStage.DRAFT.value:
            return f"generar {action['body']['n']} boceto(s)"
        return {
            "audit": "auditar la imagen (GEOMETRIC_AUDITOR)",
            "inpaint": "retocar la zona pintada",
            RenderStage.COMPOSITION.value: "generar la composición",
            RenderStage.FINAL.value: "generar el render final",
        }[kind]

    def panel_of(action: dict[str, Any]) -> Panel:
        kind = action["kind"]
        if kind in {"audit", "inpaint"}:
            return panels[RenderStage(action["stage"])]
        return panels[RenderStage(kind)]

    def hide_confirm(panel: Panel) -> dict:
        return {panel.pending: None, panel.confirm_box: gr.update(visible=False),
                panel.generate: gr.update(interactive=True)}  # fmt: skip

    async def run_action(action: dict[str, Any], active_id: str) -> tuple[str, str | None]:
        kind = action["kind"]
        if kind == "audit":
            body = await client.audit_render(active_id, action["render_id"])
            report = body["audit"]["report"]
            return (
                f"Auditoría: {report['verdict']} ({report['score']}/100) · "
                f"{euros(body['cost_eur'])}",
                action["render_id"],
            )
        if kind == "inpaint":
            body = await client.inpaint_render(
                active_id, action["render_id"], action["mask"], action["instruction"]
            )
            return f"Retoque generado · {euros(body['cost_eur'])}", body["renders"][0]["id"]
        stage = RenderStage(kind)
        body = await client.generate_renders(active_id, stage, action["body"])
        first = body["renders"][0]["id"] if body["renders"] else None
        return (
            f"{stage.label}: {len(body['renders'])} imagen(es) · {euros(body['cost_eur'])}",
            first,
        )

    async def execute(action: dict[str, Any], active_id: str | None, *shown: str | None) -> dict:
        panel = panel_of(action)
        if not active_id:
            return {**empty_view(), **hide_confirm(panel)}
        if warnings := alert_lines(await client.cost_alerts(), active_id):
            gr.Warning(" ".join(warnings))  # B-021: solo avisa, la acción continúa
        gr.Info(f"En marcha: {describe(action)}… puede tardar hasta un minuto")
        try:
            message, new_render = await run_action(action, active_id)
        except ApiError as exc:
            gr.Warning(exc.detail)
            return {**await view(active_id, *shown), **hide_confirm(panel)}
        gr.Info(message)
        updated = list(shown)
        if new_render:
            updated[STAGES.index(panel.stage)] = new_render
        return {**await view(active_id, *updated), **hide_confirm(panel)}

    async def request(action: dict[str, Any], active_id: str | None, current_mode: str | None,
                      *shown: str | None) -> dict:  # fmt: skip
        panel = panel_of(action)
        project_inputs = 0
        if action["kind"] == RenderStage.DRAFT.value and active_id:
            try:
                project_inputs = draft_inputs(await client.get_project(active_id))
            except ApiError:
                project_inputs = 0
        cost = estimate(action, project_inputs)
        if needs_confirmation(current_mode, cost):
            gr.Info(f"Pendiente de confirmar: ≈ {cost:.3f} €")
            return {
                panel.pending: action,
                panel.confirm_box: gr.update(visible=True),
                panel.confirm_md: (
                    f"⚠️ Vas a **{describe(action)}** en **Azure**: coste estimado ≈ "
                    f"**{cost:.3f} €**. ¿Confirmas?"
                ),
                panel.generate: gr.update(interactive=False),
            }
        return await execute(action, active_id, *shown)

    def wire(button: gr.Button, build: Callable[..., dict[str, Any]], *inputs: Any) -> None:
        async def handler(active_id, current_mode, *values):
            shown = values[: len(STAGES)]
            action = build(shown, *values[len(STAGES) :])
            if action.get("error"):
                gr.Warning(action["error"])
                return {notice: gr.skip()}
            return await request(action, active_id, current_mode, *shown)

        button.click(handler, inputs=[*common, *inputs], outputs=outputs)

    # --- Acciones sin coste ----------------------------------------------------------------------

    def select_handler(stage: RenderStage):
        async def handler(active_id, current_mode, *shown):
            render_id = shown[STAGES.index(stage)]
            if active_id and render_id:
                try:
                    await client.select_render(active_id, render_id)
                    gr.Info(f"Imagen seleccionada ({stage.label.lower()})")
                except ApiError as exc:
                    gr.Warning(exc.detail)
            return await view(active_id, *shown)

        return handler

    def gallery_handler(stage: RenderStage):
        async def handler(evt: gr.SelectData, active_id, current_mode, *values):
            shown, ids = list(values[: len(STAGES)]), values[len(STAGES)]
            shown[STAGES.index(stage)] = ids[evt.index]
            return await view(active_id, *shown)

        return handler

    def confirm_handler(panel: Panel):
        async def handler(action, active_id, current_mode, *shown):
            if not action:
                return hide_confirm(panel)
            return await execute(action, active_id, *shown)

        return handler

    async def on_inpaint(active_id, current_mode, *values):
        shown = values[: len(STAGES)]
        editor_value, text = values[len(STAGES) :]
        mask = editor_mask(editor_value)
        if mask is None:
            gr.Warning("Pinta en la imagen la zona que quieres cambiar")
            return {notice: gr.skip()}
        if not (text or "").strip():
            gr.Warning("Describe el cambio que quieres en la zona pintada")
            return {notice: gr.skip()}
        action = {"kind": "inpaint", "stage": RenderStage.COMPOSITION.value, "mask": mask,
                  "render_id": shown[STAGES.index(RenderStage.COMPOSITION)],
                  "instruction": text.strip()}  # fmt: skip
        return await request(action, active_id, current_mode, *shown)

    # --- Salidas y eventos -----------------------------------------------------------------------

    outputs: list[gr.components.Component] = [
        notice, mode, refs, refs_md, selected_draft, selected_composition, composition_tab,
        final_tab, comp_source, final_source, textures, comp_audit, final_audit, comp_audit_cost,
        final_audit_cost, comp_audit_md, final_audit_md,
        *(c for panel in panels.values() for c in panel.components()),
    ]  # fmt: skip

    wire(
        panels[RenderStage.DRAFT].generate,
        lambda shown, n, quality, size, extra: {
            "kind": RenderStage.DRAFT.value,
            "body": {
                "n": int(n),
                "quality": quality,
                "size": size,
                "extra_instructions": extra or "",
            },
        },
        draft_n,
        draft_quality,
        draft_size,
        draft_extra,
    )
    wire(
        panels[RenderStage.COMPOSITION].generate,
        lambda shown, quality, extra, draft_id: (
            {
                "kind": RenderStage.COMPOSITION.value,
                "body": {
                    "quality": quality,
                    "extra_instructions": extra or "",
                    "draft_id": draft_id,
                },
            }
            if draft_id
            else {"error": "Selecciona un boceto para componer"}
        ),
        comp_quality,
        comp_extra,
        selected_draft,
    )
    wire(
        panels[RenderStage.FINAL].generate,
        lambda shown, refs_v, extra, composition_id: (
            {
                "kind": RenderStage.FINAL.value,
                "body": {
                    "composition_id": composition_id,
                    "reference_ids": refs_v or [],
                    "extra_instructions": extra or "",
                },
            }
            if composition_id
            else {"error": "Selecciona una composición"}
        ),
        textures,
        final_extra,
        selected_composition,
    )
    for button, stage in ((comp_audit, RenderStage.COMPOSITION), (final_audit, RenderStage.FINAL)):
        wire(
            button,
            lambda shown, stage=stage: {
                "kind": "audit",
                "stage": stage.value,
                "render_id": shown[STAGES.index(stage)],
            },
        )

    for stage, panel in panels.items():
        panel.select_btn.click(select_handler(stage), inputs=common, outputs=outputs)
        panel.gallery.select(gallery_handler(stage), inputs=[*common, panel.ids], outputs=outputs)
        panel.confirm_btn.click(
            confirm_handler(panel), inputs=[panel.pending, *common], outputs=outputs
        )
        panel.cancel_btn.click(
            lambda panel=panel: hide_confirm(panel),
            outputs=[panel.pending, panel.confirm_box, panel.generate],
        )

    def remount(nonce: int) -> int:
        return nonce + 1

    for trigger in (composition_tab.select, retouch_box.expand, comp_shown.change):
        trigger(remount, inputs=editor_nonce, outputs=editor_nonce)

    async def refresh_all(active_id: str | None) -> dict:
        return await view(active_id, None, None, None)

    async def show_render(active_id: str | None, render_id: str | None) -> dict:
        return await view(active_id, render_id, render_id, render_id)

    return StudioTab(refresh_all, outputs, show_render)
