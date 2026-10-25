"""Tema visual (decisión D5): oscuro premium zinc/slate, dark mode forzado."""

import gradio as gr

BACKGROUND = "#0a0a0a"
SURFACE = "#111113"
BORDER = "#27272a"
INPUT = "#18181b"
TEXT = "#fafafa"

# Gradio activa el modo oscuro con la clase `dark` en <body>; se fuerza al cargar. Además, los
# tooltips de la ficha (Paso 23): las casillas muestran solo el nombre y el detalle se pone como
# `title` de cada una, leído del contenedor oculto `#iai-sheet-tips` cada vez que cambia la página.
FORCE_DARK_JS = """() => {
    document.body.classList.add('dark');
    const apply = () => {
        const holder = document.querySelector('#iai-sheet-tips [data-tips]');
        const tips = holder ? JSON.parse(holder.dataset.tips || '{}') : {};
        document.querySelectorAll('[id^="iai-sheet-"] label').forEach((label) => {
            const group = label.closest('[id^="iai-sheet-"]').id.replace('iai-sheet-', '');
            const siblings = label.parentElement.querySelectorAll(':scope > label');
            const index = [...siblings].indexOf(label);
            const tip = (tips[group] || [])[index] || '';
            if (label.title !== tip) label.title = tip;
        });
    };
    new MutationObserver(apply).observe(document.body, {childList: true, subtree: true});
}"""

CSS = f"""
.gradio-container {{ max-width: 1440px !important; margin: 0 auto; }}
.iai-header {{
    display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
    gap: 1rem; padding: 0.25rem 0 0.5rem;
}}
.iai-header h1 {{ font-size: 1.75rem; font-weight: 600; letter-spacing: -0.02em; margin: 0; }}
.iai-header p {{ color: #a1a1aa; margin: 0.25rem 0 0; }}
.iai-badges {{
    display: flex; flex-wrap: wrap; gap: 0.5rem; justify-content: flex-end; margin-left: auto;
}}
.iai-badge {{
    display: inline-flex; align-items: center; gap: 0.5rem;
    padding: 0.35rem 0.75rem; border-radius: 999px;
    border: 1px solid {BORDER}; background: {SURFACE}; font-size: 0.875rem;
}}
.iai-dot {{ width: 0.5rem; height: 0.5rem; border-radius: 999px; }}
.iai-ok .iai-dot {{ background: #22c55e; }}
.iai-warn {{ border-color: #92400e; color: #fcd34d; }}
.iai-warn .iai-dot {{ background: #f59e0b; }}
.iai-error {{ border-color: #7f1d1d; color: #fca5a5; }}
.iai-error .iai-dot {{ background: #ef4444; }}
.iai-pending .iai-dot, .iai-neutral .iai-dot {{ background: #71717a; }}
/* Indicadores de la pestaña Costes. */
.iai-kpis {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.75rem;
}}
.iai-kpi {{
    display: flex; flex-direction: column; gap: 0.25rem; padding: 0.9rem 1rem;
    border: 1px solid {BORDER}; border-radius: 0.75rem; background: {SURFACE};
}}
.iai-kpi span {{ color: #a1a1aa; font-size: 0.8rem; }}
.iai-kpi strong {{ font-size: 1.35rem; font-weight: 600; }}
.iai-muted {{ color: #a1a1aa; font-size: 0.875rem; }}
/* Galería de proyectos: tarjetas 3:2 de ancho fijo mínimo y pie siempre visible. */
/* Registro de Costes IA (B-033): letra compacta para que quepan todas las columnas. */
#iai-cost-table table, #iai-cost-table table * {{
    font-size: 0.75rem !important; word-break: normal !important; overflow-wrap: normal !important;
    hyphens: none !important;
}}
/* Llamadas del proyecto (B-027): compactas para caber en media pantalla. */
#iai-project-calls table {{ width: 100%; }}
#iai-project-calls th, #iai-project-calls td {{
    font-size: 0.8rem !important; padding: 0.3rem 0.5rem !important; white-space: nowrap;
}}
.iai-gallery .grid-container {{
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)) !important;
    grid-auto-rows: auto !important; gap: 1rem !important;
}}
.iai-gallery .grid-wrap {{
    min-height: 0 !important; max-height: none !important; height: auto !important;
}}
.iai-gallery .thumbnail-item {{
    aspect-ratio: 3 / 2; height: auto !important; border: 1px solid {BORDER} !important;
    border-radius: 10px; overflow: hidden;
}}
.iai-gallery .thumbnail-item:hover {{ border-color: #52525b !important; }}
/* Miniaturas pequeñas: lo enviado al modelo, en «Ver más» (B-047). */
.iai-gallery.iai-small .grid-container {{
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)) !important; gap: 0.5rem !important;
}}
.iai-gallery .thumbnail-item.selected {{ border-color: {TEXT} !important; }}
.iai-gallery .caption-label {{
    opacity: 1 !important; left: 0 !important; right: 0 !important; bottom: 0 !important;
    max-width: none !important; border-radius: 0 !important; padding: 0.4rem 0.6rem !important;
    background: rgba(10, 10, 10, 0.78) !important; color: {TEXT} !important;
    font-size: 0.85rem !important; text-align: left !important;
}}
.iai-danger {{ background: #7f1d1d !important; color: #fef2f2 !important; }}
/* Editor de máscaras (B-039): rojo fijo sin control de paleta y el tamaño del pincel como dos
   circunferencias concéntricas (controles internos del ImageEditor: lo comprueba el E2E). */
#iai-inpaint-editor button[aria-label="Color"] {{ display: none !important; }}
#iai-inpaint-editor button[aria-label="Brush Size"] svg {{ display: none !important; }}
#iai-inpaint-editor button[aria-label="Brush Size"] > div {{
    display: flex; align-items: center; justify-content: center;
}}
#iai-inpaint-editor button[aria-label="Brush Size"] > div::after {{
    content: ""; width: 14px; height: 14px; border-radius: 50%;
    border: 2px solid currentColor; box-sizing: border-box;
    background: radial-gradient(circle, transparent 0 1.5px, currentColor 1.5px 3px,
                                transparent 3px);
}}
.iai-hidden {{ display: none !important; }}
/* Ficha de la referencia: solo nombres; el detalle, en el tooltip (Paso 23). */
#iai-sheet-tips {{ display: none !important; }}
[id^="iai-sheet-"] label[title]:not([title=""]) {{ cursor: help; }}
/* Miniaturas de lo que recibe cada generación (Paso 23): las que no caben, con el pie en rojo. */
.iai-thumbs {{ display: flex; flex-wrap: wrap; gap: 0.5rem; }}
.iai-thumb {{
    position: relative; width: 168px; aspect-ratio: 3 / 2; margin: 0; overflow: hidden;
    border: 1px solid {BORDER}; border-radius: 8px; background: {SURFACE};
}}
.iai-thumb img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
.iai-thumb figcaption {{
    position: absolute; left: 0; right: 0; bottom: 0; padding: 0.25rem 0.45rem;
    background: rgba(10, 10, 10, 0.78); color: {TEXT}; font-size: 0.72rem;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.iai-thumb.start {{ border-color: #a1a1aa; }}
.iai-thumb.excluded img {{ opacity: 0.5; }}
.iai-thumb.excluded figcaption {{ color: #f87171; font-weight: 600; }}
/* Imagen grande: el ancho de su columna y la altura según su proporción (sin caja fija). */
.iai-viewer, .iai-viewer .image-container, .iai-viewer .image-frame,
.iai-viewer button {{ height: auto !important; max-height: none !important; }}
.iai-viewer img {{
    width: 100% !important; height: auto !important; max-height: none !important;
    object-fit: contain !important;
}}
/* Barras de desplazamiento oscuras (la clara por defecto desentonaba). */
* {{ scrollbar-color: #3f3f46 {BACKGROUND}; scrollbar-width: thin; }}
::-webkit-scrollbar {{ width: 10px; height: 10px; }}
::-webkit-scrollbar-track {{ background: {BACKGROUND}; }}
::-webkit-scrollbar-thumb {{ background: #3f3f46; border-radius: 6px; }}
::-webkit-scrollbar-thumb:hover {{ background: #52525b; }}
/* Galerías sin hueco vacío bajo las tarjetas. */
.iai-gallery, .iai-gallery .gallery-container {{
    min-height: 0 !important; height: auto !important;
}}
"""


def build_theme() -> gr.themes.Base:
    return gr.themes.Base(
        primary_hue="zinc",
        secondary_hue="slate",
        neutral_hue="slate",
        radius_size="md",
        font=("Inter", "ui-sans-serif", "system-ui", "sans-serif"),
    ).set(
        body_background_fill_dark=BACKGROUND,
        body_text_color_dark=TEXT,
        background_fill_primary_dark=BACKGROUND,
        background_fill_secondary_dark=SURFACE,
        block_background_fill_dark=SURFACE,
        block_border_color_dark=BORDER,
        border_color_primary_dark=BORDER,
        button_primary_background_fill_dark=TEXT,
        button_primary_background_fill_hover_dark="#e4e4e7",
        button_primary_text_color_dark=BACKGROUND,
        # Campos y botones secundarios en zinc casi negro (el `slate` por defecto azulea).
        input_background_fill_dark=INPUT,
        input_background_fill_focus_dark=INPUT,
        input_background_fill_hover_dark=INPUT,
        input_border_color_dark=BORDER,
        input_border_color_focus_dark="#52525b",
        input_border_color_hover_dark="#3f3f46",
        button_secondary_background_fill_dark=BORDER,
        button_secondary_background_fill_hover_dark="#3f3f46",
        button_secondary_border_color_dark="#3f3f46",
        button_secondary_text_color_dark=TEXT,
        block_label_background_fill_dark=SURFACE,
    )
