"""Pestaña Estudio: ciclo Human-in-the-Loop completo del proyecto activo.

① Brief (generar, editar prompts, aprobar, rechazar) → ② Bocetos → ③ Composición →
④ Render final, con un visor común para seleccionar, descartar, rechazar con comentarios,
auditar y retocar una zona pintada (composición y render final). Las acciones de IA muestran
su coste; en modo Azure, las de más de 0,05 € piden un segundo clic de confirmación.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

import gradio as gr

from shared.models import AssetKind, BriefStatus, ProjectMetadata, RenderStage, RenderStatus
from ui.api_client import ApiError, BackendClient
from ui.cost_views import alert_lines, chain_cost_md
from ui.covers import asset_path, placeholder
from ui.studio_views import (
    COST_AUDIT,
    COST_BRIEF,
    COST_INPAINT,
    COST_PER_IMAGE,
    approved_brief,
    audit_markdown,
    brief_choices,
    brief_markdown,
    can_use_raw,
    cost_hint,
    editor_mask,
    euros,
    inpaint_file_captions,
    inpaint_hint,
    latest_brief,
    needs_confirmation,
    reference_choices,
    render_caption,
    render_detail_md,
    renders_of,
    selected_choices,
)

NO_PROJECT = "### Ningún proyecto activo\nElige o crea un proyecto en la pestaña **Proyectos**."
AUDITABLE = {RenderStage.COMPOSITION, RenderStage.FINAL}
STAGES = (RenderStage.DRAFT, RenderStage.COMPOSITION, RenderStage.FINAL)


@dataclass
class StudioTab:
    refresh_all: Callable[[str | None], Awaitable[dict]]
    all_outputs: list[gr.components.Component]
    show_render: Callable[[str | None, str | None], Awaitable[dict]]  # vista con un render


def estimate(action: dict[str, Any]) -> float:
    kind = action["kind"]
    if kind in {"brief", "reject_brief"}:
        return COST_BRIEF
    if kind == "audit":
        return COST_AUDIT
    if kind == "reject_render":
        return COST_PER_IMAGE[RenderStage(action["stage"])]
    if kind == "inpaint":
        return COST_INPAINT[RenderStage(action["stage"])]
    return COST_PER_IMAGE[RenderStage(kind)] * action.get("n", 1)


def describe(action: dict[str, Any]) -> str:
    return {
        "brief": "generar un brief",
        "reject_brief": "rechazar el brief y generar una nueva versión",
        "audit": "auditar la imagen (GEOMETRIC_AUDITOR)",
        "reject_render": "rechazar la imagen y regenerarla",
        "inpaint": "retocar la zona pintada",
        RenderStage.DRAFT.value: f"generar {action.get('n', 1)} boceto(s)",
        RenderStage.COMPOSITION.value: "generar la composición",
        RenderStage.FINAL.value: "generar el render final",
    }[action["kind"]]


def build_studio_tab(client: BackendClient, data_dir: Path, active: gr.BrowserState) -> StudioTab:
    # Etapa de cada render (para estimar el coste de rechazar y regenerar) e imagen del render
    # mostrado (para el editor de retoques); los rellena view().
    stages_by_render: dict[str, str] = {}
    shown_images: dict[str, Any] = {}

    mode = gr.State(None)
    shown_brief = gr.State(None)
    shown_render = gr.State(None)
    pending = gr.State(None)
    heading = gr.Markdown(NO_PROJECT)

    with gr.Column(visible=False) as confirm_box:
        confirm_md = gr.Markdown()
        with gr.Row():
            confirm_btn = gr.Button("Confirmar (con coste)", elem_classes="iai-danger")
            cancel_btn = gr.Button("Cancelar", variant="secondary")

    # ① Brief ----------------------------------------------------------------------------
    with gr.Accordion("① Brief de diseño", open=True) as brief_section:
        brief_select = gr.Dropdown(label="Versión", choices=[], elem_id="iai-brief-version")
        brief_md = gr.Markdown()
        with gr.Accordion(
            "Prompts de imagen (inglés; editables mientras el brief está propuesto)", open=False
        ):
            prompt_fast = gr.Textbox(
                label="Boceto (FAST_DRAFT)", lines=4, elem_id="iai-prompt-fast"
            )
            prompt_struct = gr.Textbox(label="Composición (STRUCTURAL_COMPOSER)", lines=5)
            prompt_photo = gr.Textbox(label="Render final (PHOTOREALISTIC_RENDERER)", lines=5)
            save_prompts = gr.Button(
                "Guardar prompts", variant="secondary", elem_id="iai-save-prompts"
            )
        with gr.Row():
            approve = gr.Button("Aprobar brief", variant="primary", elem_id="iai-approve-brief")
        brief_feedback = gr.Textbox(
            label="Comentarios para rechazar (y respuestas a las preguntas abiertas)", lines=2
        )
        reject_brief = gr.Button("Rechazar y generar nueva versión", variant="secondary")
        instructions = gr.Textbox(label="Indicaciones para generar un brief nuevo (opcional)")
        with gr.Row(equal_height=True):
            generate_brief = gr.Button(
                "Generar brief", variant="secondary", elem_id="iai-gen-brief"
            )
            brief_cost = gr.Markdown()

    # ② ③ ④ Etapas de imagen -------------------------------------------------------------------
    with gr.Accordion("② Bocetos (FAST_DRAFT)", open=True):
        with gr.Row():
            draft_n = gr.Slider(1, 4, value=2, step=1, label="Variantes")
            draft_quality = gr.Dropdown(["low", "medium", "high"], value="low", label="Calidad")
        draft_extra = gr.Textbox(label="Indicaciones adicionales (opcional)")
        with gr.Row(equal_height=True):
            generate_drafts = gr.Button(
                "Generar bocetos", variant="primary", elem_id="iai-gen-drafts"
            )
            drafts_cost = gr.Markdown()
        drafts_gallery = gr.Gallery(
            show_label=False, columns=4, height="auto", object_fit="cover", allow_preview=False,
            buttons=[], elem_classes="iai-gallery", elem_id="iai-drafts",
        )  # fmt: skip
        drafts_ids = gr.State([])
    with gr.Accordion("③ Composición (STRUCTURAL_COMPOSER)", open=True):
        draft_choice = gr.Dropdown(label="Boceto de referencia (seleccionados)", choices=[])
        composition_extra = gr.Textbox(label="Indicaciones adicionales (opcional)")
        with gr.Row(equal_height=True):
            generate_composition = gr.Button(
                "Generar composición", variant="primary", elem_id="iai-gen-composition"
            )
            composition_cost = gr.Markdown()
        compositions_gallery = gr.Gallery(
            show_label=False, columns=4, height="auto", object_fit="cover", allow_preview=False,
            buttons=[], elem_classes="iai-gallery", elem_id="iai-compositions",
        )  # fmt: skip
        compositions_ids = gr.State([])
    with gr.Accordion("④ Render final (PHOTOREALISTIC_RENDERER)", open=True):
        composition_choice = gr.Dropdown(label="Composición (seleccionadas)", choices=[])
        references = gr.CheckboxGroup(label="Referencias de textura y color", choices=[])
        final_extra = gr.Textbox(label="Indicaciones adicionales (opcional)")
        with gr.Row(equal_height=True):
            generate_final = gr.Button(
                "Generar render final", variant="primary", elem_id="iai-gen-final"
            )
            final_cost = gr.Markdown()
        finals_gallery = gr.Gallery(
            show_label=False, columns=4, height="auto", object_fit="cover", allow_preview=False,
            buttons=[], elem_classes="iai-gallery", elem_id="iai-finals",
        )  # fmt: skip
        finals_ids = gr.State([])

    # Visor --------------------------------------------------------------------------------------
    with gr.Accordion("Visor", open=True):
        with gr.Row(equal_height=False):
            with gr.Column(scale=3):
                viewer = gr.Image(
                    show_label=False,
                    interactive=False,
                    height=560,
                    buttons=["download", "fullscreen"],
                )
            with gr.Column(scale=2):
                viewer_md = gr.Markdown()
                with gr.Row():
                    select_btn = gr.Button("Seleccionar", variant="primary", elem_id="iai-select")
                    discard_btn = gr.Button("Descartar", variant="secondary")
                render_feedback = gr.Textbox(
                    label="Comentarios para rechazar", lines=2, elem_id="iai-render-feedback"
                )
                apply_audit = gr.Checkbox(
                    value=True, label="Aplicar las correcciones de la última auditoría"
                )
                with gr.Row():
                    reject_regenerate = gr.Button(
                        "Rechazar y regenerar", variant="secondary", elem_id="iai-reject-render"
                    )
                    reject_only = gr.Button("Rechazar sin regenerar", variant="secondary")
                with gr.Row(equal_height=True):
                    audit_btn = gr.Button("Auditar", variant="secondary", elem_id="iai-audit")
                    audit_cost = gr.Markdown()
        audit_md = gr.Markdown()
        # Si la imagen es un retoque: lo que hizo el modelo frente a lo que conservamos.
        inpaint_files = gr.Gallery(
            label="Retoque: salida en bruto del modelo, guía enviada y máscara", columns=3,
            height="auto", object_fit="contain", visible=False, elem_classes="iai-gallery",
            elem_id="iai-inpaint-files",
        )  # fmt: skip
        use_raw_btn = gr.Button(
            "Usar salida en bruto como imagen nueva (sin coste)", variant="secondary",
            visible=False, elem_id="iai-use-raw",
        )  # fmt: skip
        with gr.Accordion("Retocar zona (composición y render final)", open=False):
            gr.Markdown(
                "Pinta la zona que quieres cambiar y describe el cambio; si añades un objeto, "
                "pinta **algo más grande que el objeto** (lo que se salga de la zona se corta). "
                "Fuera de lo pintado la imagen queda **idéntica**; el retoque es una imagen nueva "
                "de la misma etapa que puedes seleccionar, descartar o rechazar (se repite con la "
                "misma zona). La salida en bruto del modelo también se guarda."
            )

            # Un editor nuevo por imagen: cambiar por código el valor de un ImageEditor ya
            # montado lo deja (una vez sí y otra no) sin la capa de trazos (Gradio 6). Solo se
            # rehace al cambiar la imagen y de uno en uno (si no, choca la `key` del editor).
            @gr.render(
                inputs=[shown_render, mode], triggers=[shown_render.change], concurrency_limit=1
            )
            def inpaint_area(render_id: str | None, current_mode: str | None) -> None:
                stage = stages_by_render.get(render_id or "")
                hint = inpaint_hint(RenderStage(stage) if stage else None, current_mode)
                image = shown_images.get(render_id or "")
                if hint is None or image is None:
                    gr.Markdown("_Elige en el visor una composición o un render final._")
                    return
                editor = gr.ImageEditor(
                    value={"background": image, "layers": [], "composite": None},
                    type="pil", format="png", sources=(), transforms=(), layers=False,
                    brush=gr.Brush(colors=[("#ef4444", 0.6)], color_mode="fixed",
                                   default_size=40),
                    eraser=gr.Eraser(default_size=40), show_label=False, height=560,
                    interactive=True, key=f"iai-editor-{render_id}",
                    elem_id="iai-inpaint-editor",
                )  # fmt: skip
                instruction = gr.Textbox(
                    label="Cambio en la zona pintada", lines=2,
                    key=f"iai-instruction-{render_id}", elem_id="iai-inpaint-instruction",
                )  # fmt: skip
                with gr.Row(equal_height=True):
                    button = gr.Button("Retocar zona", variant="primary", elem_id="iai-inpaint")
                    gr.Markdown(hint)
                wire(button, build_inpaint, editor, instruction)

    def stage_of(render_id: str | None) -> str:
        return stages_by_render.get(render_id or "", RenderStage.FINAL.value)

    galleries = {
        RenderStage.DRAFT: (drafts_gallery, drafts_ids),
        RenderStage.COMPOSITION: (compositions_gallery, compositions_ids),
        RenderStage.FINAL: (finals_gallery, finals_ids),
    }

    # --- Vista ------------------------------------------------------------------------------

    def image_of(project: ProjectMetadata, render_id: str) -> Any:
        asset = next((a for a in project.assets if str(a.id) == render_id), None)
        if asset is None:
            return placeholder("?")
        path = asset_path(data_dir, project.id, asset)
        return str(path) if path.is_file() else placeholder(asset.original_name)

    def empty_view() -> dict:
        updates: dict = {
            heading: NO_PROJECT, mode: None, shown_brief: None, shown_render: None,
            brief_select: gr.update(choices=[], value=None), brief_md: "",
            viewer: None, viewer_md: "", audit_md: "",
            inpaint_files: gr.update(value=[], visible=False),
            use_raw_btn: gr.update(visible=False),
        }  # fmt: skip
        for gallery, ids in galleries.values():
            updates |= {gallery: [], ids: []}
        for button in (generate_brief, generate_drafts, generate_composition, generate_final,
                       approve, reject_brief, save_prompts, select_btn, discard_btn,
                       reject_regenerate, reject_only, audit_btn):  # fmt: skip
            updates[button] = gr.update(interactive=False)
        return updates

    async def view(active_id: str | None, brief_id: str | None, render_id: str | None) -> dict:
        if not active_id:
            return empty_view()
        try:
            project = await client.get_project(active_id)
            health = await client.health()
        except ApiError as exc:
            gr.Warning(exc.detail)
            return empty_view()
        current_mode = health.mode
        stages_by_render.update({str(r.id): r.stage.value for r in project.renders})
        briefs = {str(b.id): b for b in project.briefs}
        brief = briefs.get(brief_id or "") or latest_brief(project)
        proposed = brief is not None and brief.status is BriefStatus.PROPOSED
        approved = approved_brief(project)
        renders = {str(r.id): r for r in project.renders}
        if render_id not in renders:
            finals = [
                r
                for r in renders_of(project, RenderStage.FINAL)
                if r.status is RenderStatus.SELECTED
            ]
            render_id = str(finals[0].id) if finals else None
        render = renders.get(render_id or "")
        chain_line = ""
        if render is not None:
            try:  # lo que ha costado llegar a esta imagen
                cost = await client.render_cost(project.id, render.id)
                chain_line = "\n\n" + chain_cost_md(cost)
            except ApiError:
                chain_line = ""
        drafts_selected = selected_choices(project, RenderStage.DRAFT)
        compositions_selected = selected_choices(project, RenderStage.COMPOSITION)

        updates: dict = {
            heading: f"### Estudio de «{project.name}»",
            mode: current_mode,
            shown_brief: str(brief.id) if brief else None,
            shown_render: render_id,
            brief_select: gr.update(
                choices=brief_choices(project), value=str(brief.id) if brief else None
            ),
            brief_md: brief_markdown(brief),
            # Plegado si el brief mostrado ya está aprobado: el trabajo sigue en las imágenes.
            brief_section: gr.update(
                open=brief is None or brief.status is not BriefStatus.APPROVED
            ),
            prompt_fast: brief.content.image_prompts.fast_draft if brief else "",
            prompt_struct: brief.content.image_prompts.structural_composer if brief else "",
            prompt_photo: brief.content.image_prompts.photorealistic_renderer if brief else "",
            save_prompts: gr.update(interactive=proposed),
            approve: gr.update(interactive=proposed),
            reject_brief: gr.update(interactive=proposed),
            generate_brief: gr.update(interactive=True),
            brief_cost: cost_hint(COST_BRIEF, current_mode),
            generate_drafts: gr.update(interactive=approved is not None),
            drafts_cost: cost_hint(COST_PER_IMAGE[RenderStage.DRAFT], current_mode) + " por imagen",
            draft_choice: gr.update(
                choices=[("Sin boceto", ""), *drafts_selected],
                value=drafts_selected[0][1] if drafts_selected else "",  # el más reciente
            ),
            generate_composition: gr.update(interactive=approved is not None),
            composition_cost: cost_hint(COST_PER_IMAGE[RenderStage.COMPOSITION], current_mode),
            composition_choice: gr.update(
                choices=compositions_selected,
                value=compositions_selected[0][1] if compositions_selected else None,
            ),
            references: gr.update(
                choices=reference_choices(project),
                value=[str(i) for i in (approved.reference_asset_ids if approved else [])],
            ),
            generate_final: gr.update(
                interactive=bool(selected_choices(project, RenderStage.COMPOSITION))
            ),
            final_cost: cost_hint(COST_PER_IMAGE[RenderStage.FINAL], current_mode),
            audit_cost: cost_hint(COST_AUDIT, current_mode),
            viewer: image_of(project, render_id) if render else None,
            viewer_md: render_detail_md(project, render) + chain_line,
            audit_md: audit_markdown(render.audits[-1] if render and render.audits else None),
            inpaint_files: gr.update(
                value=[
                    (str(data_dir / str(project.id) / AssetKind.RENDER.folder / name), caption)
                    for name, caption in inpaint_file_captions(render)
                ],
                visible=bool(render and render.inpaint),
            ),
            use_raw_btn: gr.update(visible=can_use_raw(project, render)),
            select_btn: gr.update(
                interactive=bool(render)
                and render.status in {RenderStatus.GENERATED, RenderStatus.DISCARDED}
            ),
            discard_btn: gr.update(
                interactive=bool(render)
                and render.status in {RenderStatus.GENERATED, RenderStatus.SELECTED}
            ),
            reject_regenerate: gr.update(
                interactive=bool(render) and render.status is not RenderStatus.REJECTED
            ),
            reject_only: gr.update(
                interactive=bool(render) and render.status is not RenderStatus.REJECTED
            ),
            audit_btn: gr.update(interactive=bool(render) and render.stage in AUDITABLE),
        }
        if render:
            shown_images[str(render.id)] = updates[viewer]
        for stage, (gallery, ids) in galleries.items():
            items = renders_of(project, stage)
            updates[gallery] = gr.update(
                value=[(image_of(project, str(r.id)), render_caption(r)) for r in items],
                selected_index=next(
                    (i for i, r in enumerate(items) if str(r.id) == render_id), None
                ),
            )
            updates[ids] = [str(r.id) for r in items]
        return updates

    def hide_confirm() -> dict:
        return {pending: None, confirm_box: gr.update(visible=False)}

    # --- Acciones de IA (con confirmación en Azure) -------------------------------------------

    async def run_action(
        action: dict[str, Any], active_id: str
    ) -> tuple[str, str | None, str | None]:
        kind = action["kind"]
        if kind == "brief":
            body = await client.create_brief(active_id, action["instructions"])
            return (
                f"Brief v{body['brief']['version']} generado · {euros(body['cost_eur'])}",
                body["brief"]["id"],
                None,
            )
        if kind == "reject_brief":
            body = await client.reject_brief(active_id, action["brief_id"], action["feedback"])
            new = body.get("new_brief")
            return (
                f"Brief rechazado; nueva versión generada · {euros(body['cost_eur'])}",
                new["id"] if new else None,
                None,
            )
        if kind == "audit":
            body = await client.audit_render(active_id, action["render_id"])
            report = body["audit"]["report"]
            return (
                f"Auditoría: {report['verdict']} ({report['score']}/100) · "
                f"{euros(body['cost_eur'])}",
                None,
                action["render_id"],
            )
        if kind == "reject_render":
            body = await client.reject_render(
                active_id, action["render_id"], action["feedback"], True, action["apply_audit"]
            )
            new = body["new_renders"][0]["id"] if body["new_renders"] else None
            return f"Imagen rechazada y regenerada · {euros(body['cost_eur'])}", None, new
        if kind == "inpaint":
            body = await client.inpaint_render(
                active_id, action["render_id"], action["mask"], action["instruction"]
            )
            return f"Retoque generado · {euros(body['cost_eur'])}", None, body["renders"][0]["id"]
        stage = RenderStage(kind)
        body = await client.generate_renders(active_id, stage, action["body"])
        first = body["renders"][0]["id"] if body["renders"] else None
        return (
            f"{stage.label}: {len(body['renders'])} imagen(es) · {euros(body['cost_eur'])}",
            None,
            first,
        )

    async def execute(
        action: dict[str, Any], active_id: str | None, brief_id: str | None, render_id: str | None
    ) -> dict:
        if not active_id:
            return {**empty_view(), **hide_confirm()}
        if warnings := alert_lines(await client.cost_alerts(), active_id):
            gr.Warning(" ".join(warnings))  # B-021: solo avisa, la acción continúa
        gr.Info(f"En marcha: {describe(action)}… puede tardar unos segundos")
        try:
            message, new_brief, new_render = await run_action(action, active_id)
        except ApiError as exc:
            gr.Warning(exc.detail)
            return {**await view(active_id, brief_id, render_id), **hide_confirm()}
        gr.Info(message)
        return {
            **await view(active_id, new_brief or brief_id, new_render or render_id),
            **hide_confirm(),
        }

    async def request(action: dict[str, Any], active_id: str | None, current_mode: str | None,
                      brief_id: str | None, render_id: str | None) -> dict:  # fmt: skip
        cost = estimate(action)
        if needs_confirmation(current_mode, cost):
            return {
                pending: action,
                confirm_box: gr.update(visible=True),
                confirm_md: (
                    f"⚠️ Vas a **{describe(action)}** en **Azure**: "
                    f"coste estimado ≈ **{cost:.3f} €**."
                ),
            }
        return await execute(action, active_id, brief_id, render_id)

    async def on_confirm(
        action: dict | None, active_id: str | None, brief_id: str | None, render_id: str | None
    ) -> dict:
        if not action:
            return hide_confirm()
        return await execute(action, active_id, brief_id, render_id)

    # --- Acciones sin coste ----------------------------------------------------------------------

    async def guarded(call: Callable[[], Awaitable[Any]], ok: str, active_id: str | None,
                      brief_id: str | None, render_id: str | None) -> dict:  # fmt: skip
        try:
            await call()
            gr.Info(ok)
        except ApiError as exc:
            gr.Warning(exc.detail)
        return await view(active_id, brief_id, render_id)

    common = [active, mode, shown_brief, shown_render]
    outputs: list[gr.components.Component] = [
        heading, mode, shown_brief, shown_render, pending, confirm_box, confirm_md, brief_section,
        brief_select,
        brief_md, prompt_fast, prompt_struct, prompt_photo, save_prompts, approve, reject_brief,
        generate_brief, brief_cost, generate_drafts, drafts_cost, draft_choice,
        generate_composition,
        composition_cost, composition_choice, references, generate_final, final_cost, viewer,
        viewer_md, audit_md, select_btn, discard_btn, reject_regenerate, reject_only, audit_btn,
        audit_cost, inpaint_files, use_raw_btn,
        *(c for pair in galleries.values() for c in pair),
    ]  # fmt: skip

    def on_ai(build: Callable[..., dict[str, Any]], *inputs: gr.components.Component):
        async def handler(active_id, current_mode, brief_id, render_id, *values):
            action = build(brief_id, render_id, *values)
            if action.get("error"):
                gr.Warning(action["error"])
                return {pending: gr.skip()}
            return await request(action, active_id, current_mode, brief_id, render_id)

        return handler, [*common, *inputs]

    def wire(
        button: gr.Button, build: Callable[..., dict[str, Any]], *inputs: gr.components.Component
    ) -> None:
        handler, handler_inputs = on_ai(build, *inputs)
        button.click(handler, inputs=handler_inputs, outputs=outputs)

    wire(
        generate_brief,
        lambda b, r, text: {"kind": "brief", "instructions": text or ""},
        instructions,
    )
    wire(
        reject_brief,
        lambda b, r, text: {"kind": "reject_brief", "brief_id": b, "feedback": (text or "").strip()}
        if (text or "").strip() else {"error": "Escribe tus comentarios antes de rechazar"},
        brief_feedback,
    )  # fmt: skip
    wire(
        generate_drafts,
        lambda b, r, n, q, extra: {
            "kind": RenderStage.DRAFT.value, "n": int(n),
            "body": {"n": int(n), "quality": q, "extra_instructions": extra or ""},
        },
        draft_n, draft_quality, draft_extra,
    )  # fmt: skip
    wire(
        generate_composition,
        lambda b, r, draft, extra: {
            "kind": RenderStage.COMPOSITION.value,
            "body": {"extra_instructions": extra or "", **({"draft_id": draft} if draft else {})},
        },
        draft_choice, composition_extra,
    )  # fmt: skip
    wire(
        generate_final,
        lambda b, r, composition, refs, extra: {
            "kind": RenderStage.FINAL.value,
            "body": {
                "composition_id": composition, "reference_ids": refs or [],
                "extra_instructions": extra or "",
            },
        } if composition else {"error": "Elige una composición seleccionada"},
        composition_choice, references, final_extra,
    )  # fmt: skip
    wire(audit_btn, lambda b, r: {"kind": "audit", "render_id": r})
    wire(
        reject_regenerate,
        lambda b, r, text, apply: {
            "kind": "reject_render", "render_id": r, "feedback": (text or "").strip(),
            "apply_audit": bool(apply), "stage": stage_of(r),
        } if (text or "").strip() else {"error": "Escribe tus comentarios antes de rechazar"},
        render_feedback, apply_audit,
    )  # fmt: skip

    def build_inpaint(b, r, value, text) -> dict[str, Any]:
        mask = editor_mask(value)
        if mask is None:
            return {"error": "Pinta en la imagen la zona que quieres cambiar"}
        if not (text or "").strip():
            return {"error": "Describe el cambio que quieres en la zona pintada"}
        return {
            "kind": "inpaint", "render_id": r, "stage": stage_of(r), "mask": mask,
            "instruction": text.strip(),
        }  # fmt: skip

    confirm_btn.click(
        on_confirm, inputs=[pending, active, shown_brief, shown_render], outputs=outputs
    )
    cancel_btn.click(hide_confirm, outputs=[pending, confirm_box])

    async def on_save_prompts(active_id, current_mode, brief_id, render_id, fast, struct, photo):
        prompts = {
            "fast_draft": fast,
            "structural_composer": struct,
            "photorealistic_renderer": photo,
        }
        return await guarded(
            lambda: client.update_brief(active_id, brief_id, {"image_prompts": prompts}),
            "Prompts guardados", active_id, brief_id, render_id,
        )  # fmt: skip

    async def on_approve(active_id, current_mode, brief_id, render_id):
        return await guarded(
            lambda: client.approve_brief(active_id, brief_id), "Brief aprobado",
            active_id, brief_id, render_id,
        )  # fmt: skip

    async def on_decide(select: bool, active_id, current_mode, brief_id, render_id):
        return await guarded(
            lambda: client.decide_render(active_id, render_id, select),
            ("Imagen seleccionada" if select else "Imagen descartada")
            + (" (el render final anterior pasa a descartado)"
               if select and stage_of(render_id) == RenderStage.FINAL.value else ""),
            active_id, brief_id, render_id,
        )  # fmt: skip

    async def on_reject_only(active_id, current_mode, brief_id, render_id, text):
        if not (text or "").strip():
            gr.Warning("Escribe tus comentarios antes de rechazar")
            return {pending: gr.skip()}
        return await guarded(
            lambda: client.reject_render(active_id, render_id, text.strip(), regenerate=False),
            "Imagen rechazada", active_id, brief_id, render_id,
        )  # fmt: skip

    async def on_brief_change(active_id, current_mode, brief_id, render_id, chosen):
        return await view(active_id, chosen, render_id)

    def gallery_handler(stage: RenderStage):
        async def handler(evt: gr.SelectData, active_id, current_mode, brief_id, render_id, ids):
            chosen = ids[evt.index]
            return await view(active_id, brief_id, chosen)

        return handler

    save_prompts.click(
        on_save_prompts, inputs=[*common, prompt_fast, prompt_struct, prompt_photo], outputs=outputs
    )
    approve.click(on_approve, inputs=common, outputs=outputs)
    select_btn.click(partial(on_decide, True), inputs=common, outputs=outputs)
    discard_btn.click(partial(on_decide, False), inputs=common, outputs=outputs)

    async def on_use_raw(active_id, current_mode, brief_id, render_id):
        try:
            record = await client.use_raw_output(active_id, render_id)
        except ApiError as exc:
            gr.Warning(exc.detail)
            return await view(active_id, brief_id, render_id)
        gr.Info("Salida en bruto añadida como imagen nueva (sin coste)")
        return await view(active_id, brief_id, str(record.id))

    use_raw_btn.click(on_use_raw, inputs=common, outputs=outputs)
    reject_only.click(on_reject_only, inputs=[*common, render_feedback], outputs=outputs)
    brief_select.input(on_brief_change, inputs=[*common, brief_select], outputs=outputs)
    for stage, (gallery, ids) in galleries.items():
        gallery.select(gallery_handler(stage), inputs=[*common, ids], outputs=outputs)

    async def refresh_all(active_id: str | None) -> dict:
        return {**await view(active_id, None, None), **hide_confirm()}

    async def show_render(active_id: str | None, render_id: str | None) -> dict:
        return await view(active_id, None, render_id)

    return StudioTab(refresh_all, outputs, show_render)
