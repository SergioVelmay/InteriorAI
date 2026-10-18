"""Tema visual (decisión D5): oscuro premium zinc/slate, dark mode forzado."""

import gradio as gr

BACKGROUND = "#0a0a0a"
SURFACE = "#111113"
BORDER = "#27272a"
INPUT = "#18181b"
TEXT = "#fafafa"

# Gradio activa el modo oscuro con la clase `dark` en <body>; se fuerza al cargar.
FORCE_DARK_JS = "() => { document.body.classList.add('dark'); }"

CSS = f"""
.gradio-container {{ max-width: 1440px !important; margin: 0 auto; }}
.iai-header {{
    display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
    gap: 1rem; padding: 0.25rem 0 0.5rem;
}}
.iai-header h1 {{ font-size: 1.75rem; font-weight: 600; letter-spacing: -0.02em; margin: 0; }}
.iai-header p {{ color: #a1a1aa; margin: 0.25rem 0 0; }}
.iai-badges {{ display: flex; flex-wrap: wrap; gap: 0.5rem; }}
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
.iai-soon {{ color: #a1a1aa; padding: 2rem 0; text-align: center; }}
/* Galería de proyectos: tarjetas 3:2 de ancho fijo mínimo y pie siempre visible. */
.iai-gallery .grid-container {{
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)) !important;
    grid-auto-rows: auto !important; gap: 1rem !important;
}}
.iai-gallery .grid-wrap {{ max-height: none !important; height: auto !important; }}
.iai-gallery .thumbnail-item {{
    aspect-ratio: 3 / 2; height: auto !important; border: 1px solid {BORDER} !important;
    border-radius: 10px; overflow: hidden;
}}
.iai-gallery .thumbnail-item:hover {{ border-color: #52525b !important; }}
.iai-gallery .thumbnail-item.selected {{ border-color: {TEXT} !important; }}
.iai-gallery .caption-label {{
    opacity: 1 !important; left: 0 !important; right: 0 !important; bottom: 0 !important;
    max-width: none !important; border-radius: 0 !important; padding: 0.4rem 0.6rem !important;
    background: rgba(10, 10, 10, 0.78) !important; color: {TEXT} !important;
    font-size: 0.85rem !important; text-align: left !important;
}}
.iai-danger {{ background: #7f1d1d !important; color: #fef2f2 !important; }}
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
