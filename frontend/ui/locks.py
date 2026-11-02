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
# B-111: lo que cambia el proyecto activo (elegir otro, crear uno o moverlo a la papelera) se
# bloquea mientras haya algo procesándose en cualquier pestaña, también en las que no están a la
# vista: su respuesta pintaría datos de un proyecto en otro. Gradio solo deja los «procesando»
# en la página mientras el evento sigue en marcha, a la vista o no.
PROJECT_SWITCH = "#iai-projects .thumbnail-item, #iai-create, #iai-delete, #iai-delete-confirm"
# B-113: también los controles de la pestaña a la vista (casillas, opciones, deslizadores,
# desplegables, campos de texto y el lienzo del retoque). Sin tocar su `disabled` (lo gobierna
# Gradio): se marcan, se atenúan y se anulan los clics, el arrastre y las teclas (salvo el
# tabulador) y lo que se escriba, pegue o suelte en ellos.
CONTROLS = (
    "input:not([type=hidden]), textarea, select, label, [role=listbox], #iai-inpaint-editor canvas"
)
BUSY_LOCK_JS = f"""() => {{
    const free = {json.dumps(FREE_BUTTONS)};
    const projectSwitch = {json.dumps(PROJECT_SWITCH)};
    const controls = {json.dumps(CONTROLS)};
    const shown = (el) => !!(el && el.offsetParent);
    let scheduled = false;
    const update = () => {{
        scheduled = false;
        const busy = [...document.querySelectorAll('.progress-text')].some(shown);
        const confirm = [...document.querySelectorAll('.iai-cost-confirm')].find(shown);
        const lock = busy || !!confirm;
        const anywhere = document.querySelectorAll('.progress-text').length > 0;
        document.querySelectorAll('.gradio-container button').forEach((button) => {{
            const locked = (lock && !button.matches(free) && !(confirm && confirm.contains(button)))
                || (anywhere && button.matches(projectSwitch));
            if (locked !== button.hasAttribute('data-iai-locked')) {{
                button.toggleAttribute('data-iai-locked', locked);
            }}
        }});
        document.querySelectorAll('.gradio-container').forEach((root) => {{
            root.querySelectorAll(controls).forEach((control) => {{
                const locked = lock && shown(control) && !(confirm && confirm.contains(control));
                if (locked !== control.hasAttribute('data-iai-locked')) {{
                    control.toggleAttribute('data-iai-locked', locked);
                }}
            }});
        }});
    }};
    const schedule = () => {{
        if (!scheduled) {{ scheduled = true; requestAnimationFrame(update); }}
    }};
    const block = (event) => {{
        const locked = event.isTrusted && event.target.closest
            && event.target.closest('[data-iai-locked]');
        if (locked) {{ event.preventDefault(); event.stopImmediatePropagation(); }}
    }};
    ['pointerdown', 'mousedown', 'click', 'dblclick', 'beforeinput', 'paste', 'drop']
        .forEach((type) => document.addEventListener(type, block, {{capture: true}}));
    document.addEventListener('keydown', (event) => {{
        if (event.key !== 'Tab') block(event);
    }}, {{capture: true}});
    new MutationObserver(schedule).observe(document.body, {{
        childList: true, subtree: true, characterData: true, attributes: true,
        attributeFilter: ['class', 'style', 'hidden'],
    }});
    schedule();
}}"""
