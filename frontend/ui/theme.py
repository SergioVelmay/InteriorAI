"""Tema visual (decisión D5): oscuro premium zinc/slate, dark mode forzado."""

import gradio as gr

BACKGROUND = "#0a0a0a"
SURFACE = "#111113"
BORDER = "#27272a"
INPUT = "#18181b"
TEXT = "#fafafa"
SMALL = "0.75rem"  # letra pequeña común (B-066): la de los tooltips

# Gradio activa el modo oscuro con la clase `dark` en <body>; se fuerza al cargar. Además, los
# tooltips de la ficha (Paso 23): las casillas muestran solo el nombre y el detalle se pone como
# `title` de cada una, leído del contenedor oculto `#iai-sheet-tips` cada vez que cambia la página.
# Y «processing» en español (B-063): Gradio lo escribe fijo en el indicador de progreso
# (`.progress-text`), sin traducción; solo se toca ese texto, nunca el de la página.
FORCE_DARK_JS = """() => {
    document.body.classList.add('dark');
    const progress = (node) => {
        const box = node.nodeType === 1 ? node : node.parentElement;
        const text = box && box.closest('.progress-text');
        if (text && text.textContent.includes('processing')) {
            const walker = document.createTreeWalker(text, NodeFilter.SHOW_TEXT);
            let item;
            while ((item = walker.nextNode())) {
                item.nodeValue = item.nodeValue.replace('processing', 'procesando');
            }
        }
        if (node.nodeType === 1) node.querySelectorAll('.progress-text').forEach(progress);
    };
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
    new MutationObserver((mutations) => {
        apply();
        mutations.forEach((m) => { progress(m.target); m.addedNodes.forEach(progress); });
    }).observe(document.body, {childList: true, subtree: true, characterData: true});
}"""

# Textos internos de Gradio en español sea cual sea el idioma del navegador (B-063): se
# sustituyen también los del inglés. No se traducen los del editor de máscara (su CSS y los E2E
# usan sus etiquetas en inglés).
GRADIO_TEXTS = {
    "upload_text.drop_file": "Arrastra el archivo aquí",
    "upload_text.drop_image": "Arrastra la imagen aquí",
    "upload_text.drop_gallery": "Arrastra las imágenes aquí",
    "upload_text.click_to_upload": "Haz clic para elegirlo",
    "upload_text.paste_clipboard": "Pegar del portapapeles",
    "common.or": "o",
}

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
/* Pestaña activa (B-058): en blanco y negrita, con la línea inferior también blanca. */
[role="tablist"] button[role="tab"].selected {{
    color: {TEXT} !important; font-weight: 600 !important;
}}
[role="tablist"] button[role="tab"].selected::after {{ background: {TEXT} !important; }}
/* Escala única de imágenes (B-079), como fracción del ancho total de la página: 1/1 vista previa,
   1/2 imagen en una columna del 50 %, 1/4 miniaturas de galería y 1/6 las más pequeñas. Cada
   galería declara cuántas caben por fila en su contenedor: `iai-cols-2` (galería en una columna
   del 50 %), `iai-cols-4` (galería a ancho completo), `iai-cols-3` y `iai-cols-6` (pequeñas en
   una columna del 50 % o a ancho completo). */
.iai-gallery .grid-container {{
    grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
    grid-auto-rows: auto !important; gap: 1rem !important;
}}
.iai-gallery.iai-cols-2 .grid-container {{
    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
}}
.iai-gallery.iai-cols-3 .grid-container {{
    grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
}}
.iai-gallery.iai-cols-6 .grid-container {{
    grid-template-columns: repeat(6, minmax(0, 1fr)) !important;
}}
.iai-gallery .grid-wrap {{
    min-height: 0 !important; max-height: none !important; height: auto !important;
}}
.iai-gallery .thumbnail-item {{
    aspect-ratio: 3 / 2; height: auto !important; border: 1px solid {BORDER} !important;
    border-radius: 10px; overflow: hidden;
}}
.iai-gallery .thumbnail-item:hover {{ border-color: #52525b !important; }}
/* Miniaturas pequeñas: lo enviado al modelo (B-047), con menos separación. */
.iai-gallery.iai-small .grid-container {{ gap: 0.5rem !important; }}
.iai-gallery .thumbnail-item.selected {{ border-color: {TEXT} !important; }}
.iai-gallery .caption-label {{
    opacity: 1 !important; left: 0 !important; right: 0 !important; bottom: 0 !important;
    max-width: none !important; border-radius: 0 !important; padding: 0.4rem 0.6rem !important;
    background: rgba(10, 10, 10, 0.78) !important; color: {TEXT} !important;
    font-size: {SMALL} !important; text-align: left !important;
}}
/* Referencias (B-065): pie en dos líneas, el nombre arriba y los datos abajo; cada línea se
   recorta con puntos suspensivos. */
#iai-references .caption-label {{
    white-space: pre !important; overflow: hidden !important; text-overflow: ellipsis !important;
    line-height: 1.35 !important;
}}
/* Ficha (B-066): los elementos en letra pequeña, los grupos en la normal. */
[id^="iai-sheet-"]:not([id^="iai-sheet-group-"]) label {{ font-size: {SMALL} !important; }}
/* Leyenda común de Costes IA (B-081): un rol por línea, con aire. */
.iai-legend {{ padding: 0.5rem 0.75rem; }}
.iai-legend h4 {{ color: #a1a1aa; font-size: 0.9rem; font-weight: 500; margin: 0 0 0.75rem; }}
.iai-legend ul {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 0.85rem; }}
.iai-legend li {{ display: flex; align-items: center; gap: 0.6rem; font-size: 0.95rem; }}
.iai-legend li span:not(.iai-swatch) {{ color: #a1a1aa; }}
.iai-swatch {{ width: 1rem; height: 1rem; border-radius: 3px; flex: none; }}
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
/* Miniaturas de lo que recibe cada generación (Paso 23): las que no caben, con el pie en rojo.
   Escala 1/6 (B-079): 6 por fila a ancho completo y 3 en una columna del 50 % (`iai-half`). */
.iai-thumbs {{
    display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 0.5rem;
}}
.iai-half .iai-thumbs {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
.iai-thumb {{
    position: relative; aspect-ratio: 3 / 2; margin: 0; overflow: hidden;
    border: 1px solid {BORDER}; border-radius: 8px; background: {SURFACE};
}}
.iai-thumb img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
.iai-thumb figcaption {{
    position: absolute; left: 0; right: 0; bottom: 0; padding: 0.25rem 0.45rem;
    background: rgba(10, 10, 10, 0.78); color: {TEXT}; font-size: {SMALL};
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
