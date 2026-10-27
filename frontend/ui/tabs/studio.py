"""Pestañas Bocetos, Composición y Render Final: una por etapa (B-035), de primer nivel desde el
Paso 23, que se desbloquean en orden (B-043).

① Bocetos (Paso 22): las referencias activas → generar (prompt automático, sin brief) → elegir
uno. ② Composición (Paso 23): auditoría opcional del boceto (B-046), retoque de la composición
seleccionada (B-038/039) y crear la composición a partir del boceto seleccionado o de la
composición actual (B-045, B-055). ③ Render Final (Paso 24): fotografía realista de la
composición seleccionada o del render final actual, con indicaciones globales, proporción y
resolución; «Otra versión» repite tal cual el prompt de la imagen mostrada (B-051, B-055, B-040).
En cada pestaña, la imagen seleccionada en grande con lo que entendió la IA, el prompt y lo
enviado al modelo (B-047); la confirmación de coste, junto al botón que la pide (B-049).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

import gradio as gr
from PIL import Image

from shared.models import ProjectMetadata, RenderStage, RenderStatus
from shared.sizes import DEFAULT_RATIO, DEFAULT_RENDERER_SIZE
from shared.supports import MAX_SUPPORTS, active_references
from ui.api_client import ApiError, BackendClient
from ui.cost_views import alert_lines, chain_cost_md
from ui.covers import asset_path, placeholder
from ui.forecast import FORECAST_S
from ui.studio_views import (
    COST_AUDIT,
    DRAFT_SIZES,
    QUALITIES,
    RATIOS,
    audit_markdown,
    audit_thumbs,
    composition_cost,
    composition_inputs,
    cost_hint,
    draft_cost,
    draft_inputs,
    draft_thumbs,
    editor_mask,
    euros,
    final_cost,
    needs_confirmation,
    render_caption,
    render_detail_md,
    render_inputs,
    render_thumb,
    render_title_md,
    renders_of,
    resolution_choices,
    selected_render,
    support_thumbs,
    thumbs_html,
)

NO_PROJECT = "Ningún proyecto activo: elige o crea uno en la pestaña **Proyectos**."
NO_REFERENCES = (
    "⚠️ No hay referencias activas: marca en **Referencias** lo que quieres usar de cada imagen "
    "para poder generar bocetos."
)
STAGES = (RenderStage.DRAFT, RenderStage.COMPOSITION, RenderStage.FINAL)
# «Generar con la composición actual» solo ejecuta JS: pulsa, en diferido, el botón oculto que
# toca: el puente del editor (con «Usar el retoque», envía la máscara) o el de generar sin
# retoque (un solo evento cada vez).
RETOUCH_BRIDGE_JS = """() => {
    const retouch = document.querySelector('#iai-use-retouch input')?.checked;
    const target = retouch ? '#iai-retouch-bridge' : '#iai-gen-current-plain';
    setTimeout(() => document.querySelector(target)?.click(), 0);
}"""
# Acciones con coste: su botón, la etapa cuya imagen se muestra después y su descripción.
ACTION_STAGES = {
    "boceto": RenderStage.DRAFT,
    "auditoria": RenderStage.DRAFT,
    "composicion": RenderStage.COMPOSITION,
    "composicion_actual": RenderStage.COMPOSITION,
    "render_final": RenderStage.FINAL,
    "render_final_actual": RenderStage.FINAL,
    "otra_version": RenderStage.FINAL,
}
# Previsión de tiempo de cada acción mientras Gradio no tiene historial (B-064)
ACTION_FORECASTS = {
    "boceto": FORECAST_S["bocetos"],
    "auditoria": FORECAST_S["auditoria"],
    "composicion": FORECAST_S["composicion"],
    "composicion_actual": FORECAST_S["composicion"],
    "render_final": FORECAST_S["render_final"],
    "render_final_actual": FORECAST_S["render_final"],
    "otra_version": FORECAST_S["otra_version"],
}


def layers_only(editor: gr.ImageEditor, payload: Any) -> dict[str, Any] | None:
    """`preprocess` del editor del retoque: solo las capas pintadas (la máscara).

    El fondo y la imagen compuesta no se usan y Gradio puede estar todavía escribiéndolos en su
    caché cuando llega el evento (archivos con el mismo contenido, como el fondo y la compuesta
    sin trazos, van al mismo directorio): leerlos fallaba a veces con `UnidentifiedImageError`.
    Se sustituye en la instancia: una subclase de componente genera un `.pyi` junto al código.
    """
    if payload is None:
        return None
    layers = payload.layers
    if payload.id is not None:  # capas guardadas aparte por Gradio
        cached = editor.blob_storage.pop(payload.id, None)
        layers = cached.layers if cached else []
    return {
        "background": None,
        "layers": [editor.convert_and_format_image(layer) for layer in layers or [] if layer],
        "composite": None,
    }


@dataclass
class StudioTabs:
    tabs: list[gr.Tab]
    refresh_all: Callable[[str | None], Awaitable[dict]]
    all_outputs: list[gr.components.Component]
    unlock: Callable[[str | None], Awaitable[dict]]  # solo el bloqueo de las pestañas
    unlock_outputs: list[gr.components.Component]
    show_render: Callable[[str | None, str | None], Awaitable[dict]]  # abre una imagen
    # Eventos con coste y su previsión en segundos (B-064, `ui.forecast`)
    forecasts: list[tuple[dict[str, Any], float]] = field(default_factory=list)


@dataclass
class Action:
    """Un botón con coste y su confirmación justo debajo (B-049)."""

    button: gr.Button
    cost: gr.Markdown
    confirm_box: gr.Column
    confirm_md: gr.Markdown
    confirm_btn: gr.Button
    cancel_btn: gr.Button
    pending: gr.State

    def components(self) -> list[gr.components.Component]:
        return [self.button, self.cost, self.confirm_box, self.confirm_md, self.pending]


@dataclass
class Panel:
    """Lo común de las tres pestañas: miniaturas de la etapa y la imagen mostrada."""

    stage: RenderStage
    gallery: gr.Gallery
    ids: gr.State
    viewer: gr.Image
    title: gr.Markdown
    select_btn: gr.Button
    more_md: gr.Markdown
    inputs: gr.Gallery
    chain_md: gr.Markdown
    shown: gr.State

    def components(self) -> list[gr.components.Component]:
        return [self.gallery, self.ids, self.viewer, self.title, self.select_btn, self.more_md,
                self.inputs, self.chain_md, self.shown]  # fmt: skip


def _action(label: str, slug: str, variant: str = "primary") -> Action:
    with gr.Row(equal_height=True):
        button = gr.Button(label, variant=variant, elem_id=f"iai-gen-{slug}")  # type: ignore[arg-type]
        cost = gr.Markdown(elem_classes=["iai-muted", "iai-action-note"])
    with gr.Column(visible=False, elem_id=f"iai-confirm-{slug}") as confirm_box:
        confirm_md = gr.Markdown(elem_classes="iai-action-note")
        with gr.Row():
            confirm_btn = gr.Button("Confirmar (con coste)", elem_classes="iai-danger")
            cancel_btn = gr.Button("Cancelar", variant="secondary")
    return Action(button, cost, confirm_box, confirm_md, confirm_btn, cancel_btn, gr.State(None))


def _thumbnails(slug: str, columns: int = 4) -> dict[str, Any]:
    """Galería de la etapa (B-079): 2 por fila en una columna del 50 %, 4 a ancho completo."""
    gallery = gr.Gallery(
        show_label=False, columns=columns, height="auto", object_fit="cover",
        allow_preview=False, buttons=[], elem_classes=["iai-gallery", f"iai-cols-{columns}"],
        elem_id=f"iai-{slug}",
    )  # fmt: skip
    return {"gallery": gallery, "ids": gr.State([])}


def _viewer(slug: str, *, after_select: Callable[[], None] | None = None) -> dict[str, Any]:
    """A ancho completo (B-067): la imagen grande en su proporción, su línea, «Seleccionar» y,
    debajo, la trazabilidad (lo que entendió la IA, el prompt, las imágenes enviadas al modelo en
    miniaturas de 1/6 y, al final, el coste de la cadena). `after_select` añade controles bajo
    «Seleccionar» («Otra versión»)."""
    viewer = gr.Image(
        show_label=False, interactive=False, buttons=["download", "fullscreen"],
        elem_id=f"iai-viewer-{slug}", elem_classes="iai-viewer",
    )  # fmt: skip
    title = gr.Markdown()
    select_btn = gr.Button("Seleccionar", variant="primary", elem_id=f"iai-select-{slug}")
    if after_select is not None:
        after_select()
    more_md = gr.Markdown(elem_id=f"iai-more-{slug}")
    inputs = gr.Gallery(
        label="Imágenes enviadas al modelo de imagen", columns=6, height="auto",
        object_fit="contain",
        allow_preview=False, buttons=[], elem_classes=["iai-gallery", "iai-small", "iai-cols-6"],
        elem_id=f"iai-inputs-{slug}",
    )  # fmt: skip
    chain_md = gr.Markdown(elem_id=f"iai-chain-{slug}")
    return {"viewer": viewer, "title": title, "select_btn": select_btn, "more_md": more_md,
            "inputs": inputs, "chain_md": chain_md, "shown": gr.State(None)}  # fmt: skip


def build_studio_tabs(client: BackendClient, data_dir: Path, active: gr.BrowserState) -> StudioTabs:
    """Crea las tres pestañas dentro del `gr.Tabs` de la aplicación."""
    notices: list[gr.Markdown] = []
    panels: dict[RenderStage, Panel] = {}
    forecasts: list[tuple[dict[str, Any], float]] = []
    actions: dict[str, Action] = {}
    retouch_images: dict[str, Any] = {}  # imagen de cada composición seleccionada (el editor)

    # ① Bocetos ---------------------------------------------------------------------------------
    with gr.Tab("Bocetos") as drafts_tab:
        # Estado común, dentro de una pestaña: un hijo del `gr.Tabs` que no es pestaña duplica en
        # la barra la pestaña que se selecciona (Gradio 6).
        mode = gr.State(None)
        selected_draft = gr.State(None)  # id del boceto seleccionado
        selected_composition = gr.State(None)  # composición seleccionada (la que se retoca)
        editor_nonce = gr.State(0)
        notices.append(gr.Markdown(NO_PROJECT, visible=False))
        refs_md = gr.Markdown(elem_id="iai-active-references")
        refs = gr.HTML(elem_id="iai-studio-references")
        # A ancho completo, como Composición y Render Final (B-067)
        with gr.Row():
            draft_quality = gr.Radio(QUALITIES, value="medium", label="Calidad")
            draft_size = gr.Radio(DRAFT_SIZES, value="1536x1024", label="Formato")
        draft_n = gr.Slider(1, 8, value=4, step=1, label="Variantes")
        draft_extra = gr.Textbox(
            label="Indicaciones (opcionales)", lines=2,
            placeholder="p. ej. «más cálido, tarde de otoño, alfombra de yute»",
            elem_id="iai-draft-indications",
        )  # fmt: skip
        actions["boceto"] = _action("Generar bocetos", "drafts")
        draft_gallery = _thumbnails("drafts")
        draft_view = _viewer("drafts")
        panels[RenderStage.DRAFT] = Panel(RenderStage.DRAFT, **draft_gallery, **draft_view)

    # ② Composición -----------------------------------------------------------------------------
    with gr.Tab("Composición", interactive=False) as composition_tab:
        notices.append(gr.Markdown(NO_PROJECT, visible=False))
        # Secciones opcionales plegables (B-074): cerradas, salvo la auditoría si el boceto ya
        # tiene una al abrir el proyecto o la pestaña.
        with gr.Accordion(
            "Auditoría del boceto seleccionado (opcional)", open=False,
            elem_id="iai-audit-section",
        ) as audit_box:  # fmt: skip
            gr.Markdown(
                "Compara el boceto con **todas** las referencias activas que marcan perspectiva o "
                "geometría y comprueba lo marcado en las fichas. Sus correcciones y tus "
                "observaciones se usan al crear la composición con «Usar la auditoría».",
                elem_classes="iai-muted",
            )
            audit_images = gr.HTML(elem_id="iai-audit-images")
            audit_notes = gr.Textbox(
                label="Auditoría manual: tus observaciones sobre el boceto (opcional)", lines=2,
                placeholder="p. ej. «la ventana está más a la izquierda; falta la lámpara de pie»",
                elem_id="iai-audit-notes",
            )  # fmt: skip
            actions["auditoria"] = _action("Auditar con IA", "audit", variant="secondary")
            audit_md = gr.Markdown(elem_id="iai-audit-report")

        with gr.Accordion(
            "Retoque de la composición seleccionada (opcional)", open=False,
            elem_id="iai-retouch-section",
        ) as retouch_box:  # fmt: skip
            retouch_md = gr.Markdown(elem_classes="iai-muted")

            # Contenedor del editor: se vuelve a crear con cada composición seleccionada.
            with gr.Column():
                # Un editor nuevo por imagen y al hacerse visible: cambiar por código el valor
                # de un ImageEditor montado lo deja sin la capa de trazos y, montado oculto,
                # exporta el fondo truncado (Gradio 6).
                @gr.render(
                    inputs=[selected_composition, editor_nonce], triggers=[editor_nonce.change],
                    concurrency_limit=1,
                )  # fmt: skip
                def retouch_area(render_id: str | None, nonce: int) -> None:
                    image = retouch_images.get(render_id or "")
                    if image is None:
                        return
                    if isinstance(image, str):
                        # Ya cargada: con una ruta, el editor puede reenviar el fondo truncado.
                        with Image.open(image) as opened:
                            image = opened.convert("RGB")
                    editor = gr.ImageEditor(
                        value={"background": image, "layers": [], "composite": None},
                        type="pil", format="png", sources=(), transforms=(), layers=False,
                        brush=gr.Brush(
                            colors=[("#ef4444", 0.6)], color_mode="fixed", default_size=40
                        ),
                        eraser=gr.Eraser(default_size=40), show_label=False, height=560,
                        interactive=True, key=f"iai-editor-{render_id}-{nonce}",
                        elem_id="iai-inpaint-editor",
                    )  # fmt: skip
                    # El editor solo envía su valor al pulsar: este botón oculto lo acciona
                    # «Generar con la composición actual» cuando «Usar el retoque» está marcado
                    # (sincronizarlo en cada trazo subía las capas sin parar y bloqueaba la cola).
                    editor.preprocess = partial(layers_only, editor)  # type: ignore[method-assign]
                    bridge = gr.Button("retoque", elem_id="iai-retouch-bridge",
                                       elem_classes="iai-hidden")  # fmt: skip
                    bridge.click(
                        on_retouch, outputs=outputs,
                        inputs=[*common, selected_composition, editor, retouch_instruction,
                                comp_quality, comp_extra, use_audit, audit_notes],
                    )  # fmt: skip

            retouch_instruction = gr.Textbox(
                label="Cambio en la zona pintada", lines=2,
                placeholder="p. ej. «una planta alta en la esquina, maceta de barro»",
                elem_id="iai-inpaint-instruction",
            )  # fmt: skip

        gr.Markdown("### Crear composición")
        supports_md = gr.Markdown()
        supports = gr.HTML(elem_id="iai-composition-supports")
        with gr.Row():
            comp_quality = gr.Radio(QUALITIES, value="medium", label="Calidad")
            comp_size = gr.Radio(DRAFT_SIZES, value="1536x1024", label="Formato")
        with gr.Row():
            use_audit = gr.Checkbox(
                label="Usar la auditoría (la última con IA y tus observaciones)",
                elem_id="iai-use-audit",
            )
            use_retouch = gr.Checkbox(
                label="Usar el retoque (solo con «Generar con la composición actual»)",
                elem_id="iai-use-retouch",
            )
        retouch_hint = gr.Markdown(  # B-073
            "⚠️ Con el retoque, las indicaciones solo actúan dentro de la zona pintada; para "
            "cambios globales, genera sin retoque.",
            visible=False, elem_id="iai-retouch-hint", elem_classes="iai-muted",
        )  # fmt: skip
        comp_extra = gr.Textbox(
            label="Indicaciones (opcionales)", lines=2, elem_id="iai-composition-indications"
        )
        with gr.Row(equal_height=False):
            with gr.Column(scale=1):
                start_draft = gr.HTML(elem_id="iai-start-draft", elem_classes="iai-half")
                actions["composicion"] = _action(
                    "Generar con el boceto seleccionado", "compositions"
                )
            with gr.Column(scale=1):
                start_composition = gr.HTML(
                    elem_id="iai-start-composition", elem_classes="iai-half"
                )
                actions["composicion_actual"] = _action(
                    "Generar con la composición actual", "compositions-current"
                )
                plain_current = gr.Button(  # oculto: lo pulsa RETOUCH_BRIDGE_JS
                    "generar", elem_id="iai-gen-current-plain", elem_classes="iai-hidden"
                )
        comp_gallery = _thumbnails("compositions")
        comp_view = _viewer("compositions")
        panels[RenderStage.COMPOSITION] = Panel(
            RenderStage.COMPOSITION, **comp_gallery, **comp_view
        )

    # ③ Render Final -----------------------------------------------------------------------------
    with gr.Tab("Render Final", interactive=False) as final_tab:
        notices.append(gr.Markdown(NO_PROJECT, visible=False))
        selected_final = gr.State(None)  # id del render final seleccionado
        gr.Markdown(
            "Fotografía realista con el modelo fotorrealista: recibe solo la imagen de partida y "
            "el prompt (lo marcado en las fichas va descrito en el texto). Las indicaciones son "
            "cambios globales: noche, iluminación, ambiente, personas…",
            elem_classes="iai-muted",
        )
        with gr.Row():
            final_ratio = gr.Radio(RATIOS, value=DEFAULT_RATIO, label="Proporción",
                                   elem_id="iai-final-ratio")  # fmt: skip
            final_size = gr.Radio(
                resolution_choices(DEFAULT_RATIO), value=DEFAULT_RENDERER_SIZE,
                label="Resolución", elem_id="iai-final-size",
            )  # fmt: skip
        final_extra = gr.Textbox(
            label="Indicaciones globales (opcionales)", lines=2,
            placeholder="p. ej. «de noche con las lámparas encendidas» o «una pareja leyendo»",
            elem_id="iai-final-indications",
        )  # fmt: skip
        with gr.Row(equal_height=False):
            with gr.Column(scale=1):
                start_final_composition = gr.HTML(
                    elem_id="iai-start-final-composition", elem_classes="iai-half"
                )
                actions["render_final"] = _action(
                    "Generar con la composición seleccionada", "finals"
                )
            with gr.Column(scale=1):
                start_final_current = gr.HTML(
                    elem_id="iai-start-final-current", elem_classes="iai-half"
                )
                actions["render_final_actual"] = _action(
                    "Generar con el render final actual", "finals-current"
                )
        final_gallery = _thumbnails("finals")

        def variant_controls() -> None:
            gr.Markdown(
                "**Otra versión** repite tal cual el prompt, la imagen de partida y la resolución "
                "de la imagen mostrada (sin indicaciones nuevas): el modelo varía el resultado.",
                elem_classes="iai-muted",
            )
            actions["otra_version"] = _action("Otra versión", "finals-variant", "secondary")

        final_view = _viewer("finals", after_select=variant_controls)
        panels[RenderStage.FINAL] = Panel(RenderStage.FINAL, **final_gallery, **final_view)

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
        updates: dict = {mode: None, refs: "", refs_md: "", selected_draft: None,
                         selected_composition: None, audit_images: "", audit_md: "",
                         retouch_md: "", supports_md: "", supports: "", start_draft: "",
                         start_composition: "", use_retouch: gr.update(value=False),
                         composition_tab: gr.update(interactive=False),
                         final_tab: gr.update(interactive=False), selected_final: None,
                         start_final_composition: "", start_final_current: ""}  # fmt: skip
        updates |= {notice: gr.update(visible=True) for notice in notices}
        for action in actions.values():
            updates |= {action.button: gr.update(interactive=False), action.cost: ""}
        for panel in panels.values():
            updates |= {panel.gallery: [], panel.ids: [], panel.viewer: None, panel.title: "",
                        panel.more_md: "", panel.inputs: [], panel.chain_md: "",
                        panel.shown: None,
                        panel.select_btn: gr.update(interactive=False)}  # fmt: skip
        return updates

    async def panel_updates(
        project: ProjectMetadata, stage: RenderStage, render_id: str | None
    ) -> dict:
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
                chain = chain_cost_md(await client.render_cost(project.id, render.id))
            except ApiError:
                chain = ""
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
            panel.viewer: image_of(project, render_id) if render else None,
            panel.title: render_title_md(render),
            panel.select_btn: gr.update(
                interactive=render is not None and not is_selected,
                value="Seleccionada ●" if is_selected else "Seleccionar",
            ),
            panel.more_md: render_detail_md(project, render),
            panel.inputs: render_inputs(project, render, data_dir),
            panel.chain_md: chain,
        }

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
        updates: dict = {mode: current_mode}
        updates |= {notice: gr.update(visible=False) for notice in notices}
        for stage, render_id in zip(STAGES, shown, strict=True):
            updates |= await panel_updates(project, stage, render_id)

        # Bocetos: lo que recibe el modelo (los apoyos que no caben, en rojo).
        actives = active_references(project)
        n_drafts = draft_inputs(project)
        updates[refs] = thumbs_html(draft_thumbs(project, data_dir))
        updates[refs_md] = (
            f"**Referencias activas ({len(actives)})** · se envían {n_drafts} imágenes (la base "
            f"y hasta {MAX_SUPPORTS} apoyos, primero los de perspectiva y geometría); se usa lo "
            "marcado en cada ficha."
            if actives
            else NO_REFERENCES
        )

        # Composición: auditoría del boceto, retoque y lo que recibe el modelo.
        draft = selected_render(project, RenderStage.DRAFT)
        composition = selected_render(project, RenderStage.COMPOSITION)
        if composition is not None:
            retouch_images[str(composition.id)] = image_of(project, str(composition.id))
        final = selected_render(project, RenderStage.FINAL)
        shown_final = next(
            (r for r in project.renders if str(r.id) == updates[panels[RenderStage.FINAL].shown]),
            None,
        )
        n_comp = composition_inputs(project)
        quality_note = " (1 en calidad media)"
        comp_cost = cost_hint(composition_cost("medium", n_comp), current_mode) + quality_note
        updates |= {
            selected_draft: str(draft.id) if draft else None,
            selected_composition: str(composition.id) if composition else None,
            composition_tab: gr.update(interactive=draft is not None),
            final_tab: gr.update(interactive=composition is not None),
            audit_images: thumbs_html(audit_thumbs(project, draft, data_dir)),
            audit_md: audit_markdown(draft.audits[-1] if draft and draft.audits else None, project),
            retouch_md: (
                "Pinta la zona que quieres cambiar y describe el cambio; se aplica al pulsar "
                "«Generar con la composición actual» con «Usar el retoque» marcado. El modelo "
                "edita esa zona con la máscara y devuelve la imagen completa."
                if composition
                else "_Selecciona una composición para retocarla._"
            ),
            use_retouch: gr.update(interactive=composition is not None)
            if composition
            else gr.update(interactive=False, value=False),
            supports_md: f"**Apoyos que se envían** (hasta {MAX_SUPPORTS}, primero los de "
            "perspectiva y geometría):",
            supports: thumbs_html(
                support_thumbs(project, data_dir),
                "Sin referencias activas: solo la imagen de partida.",
            ),
            start_draft: thumbs_html(render_thumb(project, draft, data_dir, "Boceto seleccionado")),
            start_composition: thumbs_html(
                render_thumb(project, composition, data_dir, "Composición actual"),
                "Selecciona una composición para partir de ella.",
            ),
            selected_final: str(final.id) if final else None,
            start_final_composition: thumbs_html(
                render_thumb(project, composition, data_dir, "Composición seleccionada"),
                "Selecciona una composición para el render final.",
            ),
            start_final_current: thumbs_html(
                render_thumb(project, final, data_dir, "Render final actual"),
                "Selecciona un render final para partir de él.",
            ),
        }
        enabled = {
            "boceto": bool(actives),
            "auditoria": draft is not None,
            "composicion": draft is not None,
            "composicion_actual": composition is not None,
            "render_final": composition is not None,
            "render_final_actual": final is not None,
            "otra_version": shown_final is not None and shown_final.prompt_info is not None,
        }
        final_hint = cost_hint(final_cost(DEFAULT_RENDERER_SIZE), current_mode) + " (a 4 MP)"
        costs = {
            "boceto": cost_hint(draft_cost(4, "medium", n_drafts), current_mode)
            + " (4 en calidad media)",
            "auditoria": cost_hint(COST_AUDIT, current_mode),
            "composicion": comp_cost,
            "composicion_actual": comp_cost,
            "render_final": final_hint,
            "render_final_actual": final_hint,
            "otra_version": cost_hint(final_cost(shown_final.size, prompt=False), current_mode)
            if shown_final
            else "",
        }
        for key, action in actions.items():
            updates |= {action.button: gr.update(interactive=enabled[key]), action.cost: costs[key]}
        return updates

    # --- Acciones de IA (confirmación junto al botón en Azure, B-049) ---------------------------

    def estimate(action: dict[str, Any], project: ProjectMetadata | None) -> float:
        kind = action["kind"]
        if kind == "auditoria":
            return COST_AUDIT
        if kind in {"render_final", "render_final_actual"}:
            return final_cost(action["body"]["size"])
        if project is None:
            return 0.0
        if kind == "otra_version":
            original = next(
                (r for r in project.renders if str(r.id) == action["body"]["variant_of"]), None
            )
            return final_cost(original.size, prompt=False) if original else 0.0
        quality = action.get("quality", "medium")
        if kind == "boceto":
            return draft_cost(action["body"]["n"], quality, draft_inputs(project))
        return composition_cost(quality, composition_inputs(project))

    def describe(action: dict[str, Any]) -> str:
        kind = action["kind"]
        if kind == "boceto":
            return f"generar {action['body']['n']} boceto(s)"
        if kind == "composicion_actual" and action.get("retouch"):
            return "retocar la zona pintada de la composición actual"
        return {
            "auditoria": "auditar el boceto (GEOMETRY_AUDITOR)",
            "composicion": "generar la composición con el boceto seleccionado",
            "composicion_actual": "generar con la composición actual",
            "render_final": "generar el render final con la composición seleccionada",
            "render_final_actual": "generar con el render final actual",
            "otra_version": "generar otra versión del render final",
        }[kind]

    def hide_confirm(action: Action) -> dict:
        return {action.pending: None, action.confirm_box: gr.update(visible=False)}

    async def run_action(action: dict[str, Any], active_id: str) -> tuple[str, str | None]:
        kind = action["kind"]
        if kind == "auditoria":
            body = await client.audit_render(active_id, action["render_id"], action["notes"])
            report = body["audit"]["report"]
            return (
                f"Auditoría: {report['verdict']} ({report['score']}/100) · "
                f"{euros(body['cost_eur'])}",
                None,
            )
        if retouch := action.get("retouch"):
            body = await client.inpaint_render(
                active_id, retouch["render_id"], retouch["mask"], retouch["instruction"],
                **action["body"],
            )  # fmt: skip
            return f"Retoque generado · {euros(body['cost_eur'])}", body["renders"][0]["id"]
        stage = ACTION_STAGES[kind]
        body = await client.generate_renders(active_id, stage, action["body"])
        first = body["renders"][0]["id"] if body["renders"] else None
        return (
            f"{stage.label}: {len(body['renders'])} imagen(es) · {euros(body['cost_eur'])}",
            first,
        )

    async def execute(action: dict[str, Any], active_id: str | None, *shown: str | None) -> dict:
        area = actions[action["kind"]]
        if not active_id:
            return {**empty_view(), **hide_confirm(area)}
        if warnings := alert_lines(await client.cost_alerts(), active_id):
            gr.Warning(" ".join(warnings))  # B-021: solo avisa, la acción continúa
        gr.Info(f"En marcha: {describe(action)}… puede tardar hasta un minuto")
        try:
            message, new_render = await run_action(action, active_id)
        except ApiError as exc:
            gr.Warning(exc.detail)
            return {**await view(active_id, *shown), **hide_confirm(area)}
        gr.Info(message)
        updated = list(shown)
        if new_render:
            updated[STAGES.index(ACTION_STAGES[action["kind"]])] = new_render
        return {**await view(active_id, *updated), **hide_confirm(area)}

    async def request(action: dict[str, Any], active_id: str | None, current_mode: str | None,
                      *shown: str | None) -> dict:  # fmt: skip
        area = actions[action["kind"]]
        project = None
        if active_id:
            try:
                project = await client.get_project(active_id)
            except ApiError:
                project = None
        cost = estimate(action, project)
        if needs_confirmation(current_mode, cost):
            gr.Info(f"Pendiente de confirmar: ≈ {cost:.3f} €")
            return {
                area.pending: action,
                area.confirm_box: gr.update(visible=True),
                area.confirm_md: (
                    f"⚠️ Vas a **{describe(action)}** en **Azure**: coste estimado ≈ "
                    f"**{cost:.3f} €**. ¿Confirmas?"
                ),
                area.button: gr.update(interactive=False),
            }
        return await execute(action, active_id, *shown)

    def wire(
        key: str,
        build: Callable[..., dict[str, Any]],
        *inputs: Any,
        trigger: gr.Button | None = None,
    ) -> None:
        async def handler(active_id, current_mode, *values):
            shown = values[: len(STAGES)]
            action = build(*values[len(STAGES) :])
            if action.get("error"):
                gr.Warning(action["error"])
                return {mode: gr.skip()}
            return await request({"kind": key, **action}, active_id, current_mode, *shown)

        dependency = (trigger or actions[key].button).click(
            handler, inputs=[*common, *inputs], outputs=outputs
        )
        forecasts.append((dependency, ACTION_FORECASTS[key]))

    async def on_retouch(active_id, current_mode, *values):
        """«Generar con la composición actual» con «Usar el retoque» (botón puente)."""
        shown = values[: len(STAGES)]
        composition_id, editor_value, instruction, quality, extra, audit_on, notes = values[
            len(STAGES) :
        ]
        mask = editor_mask(editor_value)
        error = (
            "Selecciona una composición para retocarla" if not composition_id
            else "Pinta en la imagen la zona que quieres cambiar" if mask is None
            else "Describe el cambio que quieres en la zona pintada"
            if not (instruction or "").strip() else None
        )  # fmt: skip
        if error:
            gr.Warning(error)
            return {mode: gr.skip()}
        body = composition_body(quality, None, extra, audit_on, notes)
        body.pop("size")  # el retoque conserva el tamaño de la composición
        action = {
            "kind": "composicion_actual", "quality": quality, "body": body,
            "retouch": {"render_id": composition_id, "mask": mask,
                        "instruction": instruction.strip()},
        }  # fmt: skip
        return await request(action, active_id, current_mode, *shown)

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

    def confirm_handler(key: str):
        async def handler(action, active_id, current_mode, *shown):
            if not action:
                return hide_confirm(actions[key])
            return await execute(action, active_id, *shown)

        return handler

    # --- Salidas y eventos -----------------------------------------------------------------------

    outputs: list[gr.components.Component] = [
        *notices, mode, refs, refs_md, selected_draft, selected_composition, composition_tab,
        audit_box,
        final_tab, audit_images, audit_md, retouch_md, use_retouch, supports_md, supports,
        start_draft, start_composition, selected_final, start_final_composition,
        start_final_current,
        *(c for action in actions.values() for c in action.components()),
        *(c for panel in panels.values() for c in panel.components()),
    ]  # fmt: skip

    wire(
        "boceto",
        lambda n, quality, size, extra: {
            "quality": quality,
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
        "auditoria",
        lambda draft_id, notes: (
            {"render_id": draft_id, "notes": (notes or "").strip()}
            if draft_id
            else {"error": "Selecciona un boceto para auditarlo"}
        ),
        selected_draft,
        audit_notes,
    )

    def composition_body(quality, size, extra, audit_on, notes) -> dict[str, Any]:
        body = {"quality": quality, "size": size, "extra_instructions": extra or "",
                "use_audit": bool(audit_on), "audit_notes": (notes or "").strip()}  # fmt: skip
        return body

    wire(
        "composicion",
        lambda draft_id, quality, size, extra, audit_on, notes: (
            {
                "quality": quality,
                "body": {
                    **composition_body(quality, size, extra, audit_on, notes),
                    "draft_id": draft_id,
                    "source": "boceto",
                },
            }
            if draft_id
            else {"error": "Selecciona un boceto para componer"}
        ),
        selected_draft,
        comp_quality,
        comp_size,
        comp_extra,
        use_audit,
        audit_notes,
    )

    def from_composition(composition_id, quality, size, extra, audit_on, notes):
        if not composition_id:
            return {"error": "Selecciona una composición para generar a partir de ella"}
        body = composition_body(quality, size, extra, audit_on, notes)
        return {"quality": quality, "body": {**body, "source": "composicion"}}

    wire(
        "composicion_actual", from_composition,
        selected_composition, comp_quality, comp_size, comp_extra, use_audit, audit_notes,
        trigger=plain_current,
    )  # fmt: skip
    actions["composicion_actual"].button.click(None, js=RETOUCH_BRIDGE_JS)

    def final_body(size: str | None, extra: str | None, source: str) -> dict[str, Any]:
        return {"source": source, "size": size or DEFAULT_RENDERER_SIZE,
                "extra_instructions": extra or ""}  # fmt: skip

    wire(
        "render_final",
        lambda composition_id, size, extra: (
            {"body": final_body(size, extra, "composicion")}
            if composition_id
            else {"error": "Selecciona una composición"}
        ),
        selected_composition,
        final_size,
        final_extra,
    )
    wire(
        "render_final_actual",
        lambda final_id, size, extra: (
            {"body": final_body(size, extra, "render_final")}
            if final_id
            else {"error": "Selecciona un render final para generar a partir de él"}
        ),
        selected_final,
        final_size,
        final_extra,
    )
    wire(
        "otra_version",
        lambda shown_final: (
            {"body": {"variant_of": shown_final}}
            if shown_final
            else {"error": "Elige un render final para hacer otra versión"}
        ),
        panels[RenderStage.FINAL].shown,
    )
    final_ratio.change(
        lambda ratio: gr.update(
            choices=resolution_choices(ratio), value=resolution_choices(ratio)[-1][1]
        ),
        inputs=final_ratio,
        outputs=final_size,
    )

    for key, action in actions.items():
        # El cuadro de confirmación se oculta al pulsar (B-090): el «procesando» queda junto al
        # botón de la acción y no se puede confirmar dos veces.
        confirmed = action.confirm_btn.click(
            lambda: gr.update(visible=False),
            outputs=action.confirm_box,
            queue=False,
            show_progress="hidden",
        ).then(confirm_handler(key), inputs=[action.pending, *common], outputs=outputs)
        forecasts.append((confirmed, ACTION_FORECASTS[key]))
        action.cancel_btn.click(
            lambda action=action: {
                **hide_confirm(action),
                action.button: gr.update(interactive=True),
            },
            outputs=[action.pending, action.confirm_box, action.button],
        )
    for stage, panel in panels.items():
        panel.select_btn.click(select_handler(stage), inputs=common, outputs=outputs)
        panel.gallery.select(gallery_handler(stage), inputs=[*common, panel.ids], outputs=outputs)

    def remount(nonce: int) -> int:
        return nonce + 1  # editor nuevo, sin trazos

    use_retouch.change(
        lambda on: gr.update(visible=bool(on)), inputs=use_retouch, outputs=retouch_hint
    )
    for trigger in (composition_tab.select, selected_composition.change, retouch_box.expand):
        trigger(remount, inputs=editor_nonce, outputs=editor_nonce)

    async def refresh_all(active_id: str | None) -> dict:
        """Al abrir el proyecto o la pestaña: la auditoría, abierta solo si el boceto tiene una."""
        updates = await view(active_id, None, None, None)
        draft_id = updates.get(selected_draft)
        audited = False
        if draft_id:
            project = await client.get_project(active_id)
            draft = next((r for r in project.renders if str(r.id) == draft_id), None)
            audited = bool(draft and draft.audits)
        return {**updates, audit_box: gr.update(open=audited)}

    async def unlock(active_id: str | None) -> dict:
        """Desbloqueo de Composición y Render Final al cambiar de proyecto (sin abrir Bocetos)."""
        draft = composition = None
        if active_id:
            try:
                project = await client.get_project(active_id)
            except ApiError:
                project = None
            if project is not None:
                draft = selected_render(project, RenderStage.DRAFT)
                composition = selected_render(project, RenderStage.COMPOSITION)
        return {
            composition_tab: gr.update(interactive=draft is not None),
            final_tab: gr.update(interactive=composition is not None),
        }

    async def show_render(active_id: str | None, render_id: str | None) -> dict:
        return await view(active_id, render_id, render_id, render_id)

    return StudioTabs(
        [drafts_tab, composition_tab, final_tab], refresh_all, outputs, unlock,
        [composition_tab, final_tab], show_render, forecasts,
    )  # fmt: skip
