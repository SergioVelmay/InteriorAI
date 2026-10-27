"""Migración de `metadatos.json` entre versiones del esquema.

v2 → v3 (versión 4.0.0, Paso 33, B-056): sin la compatibilidad con la v1.

- Sin briefs: los briefs de la v1 desaparecen del proyecto.
- Imágenes de la v1 (con brief, rechazadas, salidas en bruto o retoques recompuestos): se
  conservan como imágenes sueltas, con su prompt y su coste, sin la cadena de la v1 (brief,
  comentarios del rechazo, intento anterior, salida en bruto ni el retoque). Sus archivos no se
  tocan.
- Referencias: sin la ficha de la v1 (`analysis`) ni el tipo de imagen anterior (`legacy_kind`).
- Auditorías: sin la captura de la v1 con la que se compararon (`reference_asset_id`).

Los datos de la 1.0.0 (esquema 1) ya no se leen: hay que actualizarlos antes con la 3.0.0.

Se aplica al arrancar (todos los proyectos) y al restaurar un proyecto de la papelera. Antes de
escribir nada, el original se copia a `metadatos.v2.json`. Es repetible: si se corta a medias, el
siguiente arranque la completa.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.storage.atomic import write_bytes_atomic, write_json_atomic
from app.storage.paths import METADATA_FILE
from shared.models import SCHEMA_VERSION, ProjectMetadata

logger = logging.getLogger("interiorai.storage")

BACKUP_FILE = "metadatos.v2.json"

_V1_RENDER_FIELDS = frozenset(
    {"brief_id", "brief_version", "feedback", "previous_attempt_id", "raw_of_render_id"}
)
_V1_INPAINT_FIELDS = frozenset({"raw_file", "guide_file", "feather_px"})
_V1_ASSET_FIELDS = frozenset({"analysis", "legacy_kind"})


def _is_v1(render: dict[str, Any]) -> bool:
    """Imagen de la v1: con algún campo de su cadena o un retoque recompuesto."""
    if any(render.get(field) for field in _V1_RENDER_FIELDS):
        return True
    inpaint = render.get("inpaint") or {}
    return inpaint.get("method") == "regeneracion" or any(
        inpaint.get(field) is not None for field in _V1_INPAINT_FIELDS
    )


def _render(render: dict[str, Any]) -> dict[str, Any]:
    v1 = _is_v1(render)
    upgraded = {k: v for k, v in render.items() if k not in _V1_RENDER_FIELDS}
    if v1:
        upgraded.pop("inpaint", None)  # imagen suelta: sin el retoque de la v1
    elif inpaint := upgraded.get("inpaint"):
        upgraded["inpaint"] = {
            k: v for k, v in inpaint.items() if k not in _V1_INPAINT_FIELDS | {"method"}
        }
    upgraded["audits"] = [
        {k: v for k, v in audit.items() if k != "reference_asset_id"}
        for audit in render.get("audits", [])
    ]
    return upgraded


def upgrade_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Convierte el contenido de un `metadatos.json` v2 en v3 (sin tocar el disco)."""
    upgraded = {k: v for k, v in data.items() if k != "briefs"}
    upgraded["assets"] = [
        {k: v for k, v in asset.items() if k not in _V1_ASSET_FIELDS}
        for asset in data.get("assets", [])
    ]
    upgraded["renders"] = [_render(r) for r in data.get("renders", [])]
    upgraded["schema_version"] = SCHEMA_VERSION
    return upgraded


def migrate(root: Path) -> bool:
    """Migra el proyecto de `root` si está en la v2. Devuelve si migró."""
    path = root / METADATA_FILE
    try:
        raw = path.read_bytes()
        data = json.loads(raw)
    except (OSError, ValueError):
        return False  # lo notificará la lectura normal (no existe o está corrupto)
    if not isinstance(data, dict):
        return False
    if data.get("schema_version") == 1:
        logger.error(
            "Proyecto %s con datos de la 1.0.0 (esquema 1): ya no se leen. Actualízalo antes "
            "con la versión 3.0.0 de InteriorAI.",
            root.name,
        )
        return False
    if data.get("schema_version") != 2:
        return False
    backup = root / BACKUP_FILE
    if not backup.exists():  # si ya existe, un arranque anterior se cortó: se conserva
        write_bytes_atomic(backup, raw)
    metadata = ProjectMetadata.model_validate(upgrade_v2(data))
    write_json_atomic(path, metadata)
    logger.info(
        "Proyecto %s migrado al esquema v%d (original: %s)", root.name, SCHEMA_VERSION, BACKUP_FILE
    )
    return True
