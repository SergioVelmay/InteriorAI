"""Bloqueos inmediatos en el navegador (Pasos 41 y 42): un formulario se bloquea en el mismo clic,
sin esperar a la ida y vuelta al servidor; la respuesta del servidor lo desbloquea después."""

from __future__ import annotations

import json


def lock_js(*selectors: str) -> str:
    """JS de un evento: desactiva los campos y botones de `selectors` (los de dentro de cada
    elemento, o el propio elemento si es un botón) y no cambia las entradas del evento."""
    targets = json.dumps(", ".join(f"{s} textarea, {s} input, button{s}" for s in selectors))
    return f"""(...args) => {{
    document.querySelectorAll({targets}).forEach((el) => {{ el.disabled = true; }});
    return args;
}}"""


# B-110 (Paso 42): mientras se ve «procesando» en la pestaña a la vista, o hay una confirmación
# de coste abierta, sus botones y miniaturas se apagan y no responden (ni con el ratón ni con el
# teclado). Siguen libres las pestañas, los desplegables y los avisos; con una confirmación
# abierta, también sus dos botones. Los clics que hace el propio JS (puentes ocultos) no son del
# usuario (`isTrusted`) y pasan. El estilo «apagado» está en `theme.CSS`.
FREE_BUTTONS = '[role="tab"], .tab-container button, button.label-wrap, .toast-wrap button'
BUSY_LOCK_JS = f"""() => {{
    const free = {json.dumps(FREE_BUTTONS)};
    const shown = (el) => !!(el && el.offsetParent);
    let scheduled = false;
    const update = () => {{
        scheduled = false;
        const busy = [...document.querySelectorAll('.progress-text')].some(shown);
        const confirm = [...document.querySelectorAll('[id^="iai-confirm-"]')].find(shown);
        const lock = busy || !!confirm;
        document.querySelectorAll('.gradio-container button').forEach((button) => {{
            const locked = lock && !button.matches(free) && !(confirm && confirm.contains(button));
            if (locked !== button.hasAttribute('data-iai-locked')) {{
                button.toggleAttribute('data-iai-locked', locked);
            }}
        }});
    }};
    const schedule = () => {{
        if (!scheduled) {{ scheduled = true; requestAnimationFrame(update); }}
    }};
    const block = (event) => {{
        const locked = event.isTrusted && event.target.closest
            && event.target.closest('button[data-iai-locked]');
        if (locked) {{ event.preventDefault(); event.stopImmediatePropagation(); }}
    }};
    ['pointerdown', 'mousedown', 'click'].forEach((type) => {{
        document.addEventListener(type, block, {{capture: true}});
    }});
    document.addEventListener('keydown', (event) => {{
        if (event.key === 'Enter' || event.key === ' ') block(event);
    }}, {{capture: true}});
    new MutationObserver(schedule).observe(document.body, {{
        childList: true, subtree: true, characterData: true, attributes: true,
        attributeFilter: ['class', 'style', 'hidden'],
    }});
    schedule();
}}"""
