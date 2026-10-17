"""Tema visual (decisión D5): oscuro premium zinc/slate, dark mode forzado."""

import gradio as gr

BACKGROUND = "#0a0a0a"
SURFACE = "#111113"
BORDER = "#27272a"
TEXT = "#fafafa"

# Gradio activa el modo oscuro con la clase `dark` en <body>; se fuerza al cargar.
FORCE_DARK_JS = "() => { document.body.classList.add('dark'); }"

CSS = f"""
.gradio-container {{ max-width: 1280px !important; margin: 0 auto; }}
.iai-header h1 {{ font-size: 1.75rem; font-weight: 600; letter-spacing: -0.02em; margin: 0; }}
.iai-header p {{ color: #a1a1aa; margin: 0.25rem 0 0; }}
.iai-badge {{
    display: inline-flex; align-items: center; gap: 0.5rem;
    padding: 0.35rem 0.75rem; border-radius: 999px;
    border: 1px solid {BORDER}; background: {SURFACE}; font-size: 0.875rem;
}}
.iai-dot {{ width: 0.5rem; height: 0.5rem; border-radius: 999px; }}
.iai-ok .iai-dot {{ background: #22c55e; }}
.iai-warn .iai-dot {{ background: #f59e0b; }}
.iai-error .iai-dot {{ background: #ef4444; }}
.iai-pending .iai-dot {{ background: #71717a; }}
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
    )
