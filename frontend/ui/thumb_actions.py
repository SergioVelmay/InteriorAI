"""Aspa y ✓ sobre las miniaturas de Bocetos, Composición y Render final (B-109, Paso 43).

Gradio no admite botones dentro de las miniaturas de una galería: este JS, que se carga con la
página, añade un aspa (descartar) a cada candidata salvo la seleccionada y un ✓ (recuperar) a
cada descartada; al pulsarlos deja la acción en `window.__iaiThumbAction` («discard:índice» o
«restore:índice») y pulsa el botón oculto del puente de su pestaña (`studio.THUMB_BRIDGE_JS`).
Las descartadas no se abren en grande. Va después del bloqueo (B-110): con la pestaña ocupada,
el clic ya no llega aquí.
"""

from __future__ import annotations

import json

STAGE_SLUGS = ("drafts", "compositions", "finals")
THUMB_ACTIONS_JS = """() => {
    const slugs = __SLUGS__;
    const icon = (item, action, title, text) => {
        let mark = item.querySelector(':scope > .iai-thumb-action');
        if (mark && mark.dataset.action === action) return;
        if (mark) mark.remove();
        mark = document.createElement('span');
        mark.className = 'iai-thumb-action';
        mark.dataset.action = action;
        mark.title = title;
        mark.setAttribute('aria-label', title);
        mark.textContent = text;
        item.appendChild(mark);
    };
    let scheduled = false;
    const decorate = () => {
        scheduled = false;
        slugs.forEach((slug) => {
            document.querySelectorAll('#iai-' + slug + ' .thumbnail-item').forEach((item) => {
                const label = item.querySelector('.caption-label');
                if (label && label.textContent.trim().startsWith('●')) {
                    item.querySelector(':scope > .iai-thumb-action')?.remove();
                } else {
                    icon(item, 'discard', 'Descartar', '✕');
                }
            });
            document.querySelectorAll('#iai-' + slug + '-discarded .thumbnail-item').forEach(
                (item) => icon(item, 'restore', 'Recuperar', '✓'));
        });
    };
    document.addEventListener('click', (event) => {
        if (!event.isTrusted || !event.target.closest) return;
        const mark = event.target.closest('.iai-thumb-action');
        const discarded = event.target.closest('[id$="-discarded"] .thumbnail-item');
        if (!mark && !discarded) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        if (!mark) return;  // una descartada no se abre en grande: antes se recupera
        const item = mark.closest('.thumbnail-item');
        const gallery = item.closest('.iai-gallery');
        const slug = gallery.id.replace(/^iai-/, '').replace(/-discarded$/, '');
        const index = [...gallery.querySelectorAll('.thumbnail-item')].indexOf(item);
        window.__iaiThumbAction = mark.dataset.action + ':' + index;
        document.querySelector('#iai-thumb-bridge-' + slug)?.click();
    }, {capture: true});
    new MutationObserver(() => {
        if (!scheduled) { scheduled = true; requestAnimationFrame(decorate); }
    }).observe(document.body, {childList: true, subtree: true});
    decorate();
}""".replace("__SLUGS__", json.dumps(list(STAGE_SLUGS)))
