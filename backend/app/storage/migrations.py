"""Migración de `metadatos.json` entre versiones del esquema.

v1 → v2 (versión 2.0.0, Paso 17):

- Proyecto (B-026): sin tipo de espacio, notas de diseño, dimensiones, estilo ni presupuesto; lo
  que tuvieran se añade al final de la descripción, una línea por campo con valor.
- Estados (B-048): los renders descartados o rechazados vuelven a `generado` (los comentarios
  del rechazo se conservan como historia).
- Imágenes (B-028): un solo tipo. Capturas de SketchUp y planos pasan a referencias (con su tipo
  anterior en `legacy_kind`) y sus archivos se renombran a `referencias/`.

Se aplica al arrancar (todos los proyectos) y al restaurar un proyecto de la papelera. Antes de
escribir nada, el original se copia a `metadatos.v1.json`; los archivos se mueven con un
renombrado, nunca se borran. Es repetible: si se corta a medias, el siguiente arranque la
completa.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.storage.atomic import replace_with_retry, write_bytes_atomic, write_json_atomic
from app.storage.paths import METADATA_FILE
from shared.models import SCHEMA_VERSION, ProjectMetadata

logger = logging.getLogger("interiorai.storage")

BACKUP_FILE = "metadatos.v1.json"

# Etiquetas de los tipos de espacio de la v1 (el enum ya no existe).
_SPACE_LABELS = {
    "salon_cocina_comedor": "Salón-cocina-comedor",
    "salon": "Salón",
    "cocina": "Cocina",
    "comedor": "Comedor",
    "dormitorio": "Dormitorio",
    "estudio": "Estudio",
    "bano": "Baño",
    "terraza": "Terraza",
    "otro": "Otro",
}

_V1_PROJECT_FIELDS = frozenset({"space_type", "design_notes", "dimensions", "style", "budget_eur"})
# Carpetas de los tipos de imagen que desaparecen en la v2.
_V1_FOLDERS = {"captura_sketchup": "capturas_sketchup", "plano": "planos"}
REFERENCE_FOLDER = "referencias"

Move = tuple[str, str]  # (carpeta/archivo origen, carpeta/archivo destino), relativos al proyecto


def _number(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _description(data: dict[str, Any]) -> str:
    """Descripción v2: la de la v1 y, debajo, los campos eliminados que tenían valor."""
    lines = []
    if space_type := data.get("space_type"):
        lines.append(f"Tipo de espacio: {_SPACE_LABELS.get(space_type, space_type)}")
    if notes := (data.get("design_notes") or "").strip():
        lines.append(f"Notas de diseño: {notes}")
    if dimensions := data.get("dimensions"):
        size = f"{_number(dimensions['width_m'])} x {_number(dimensions['length_m'])} m"
        if dimensions.get("height_m"):
            size += f" x {_number(dimensions['height_m'])} m de alto"
        lines.append(f"Dimensiones: {size}")
    if style := (data.get("style") or "").strip():
        lines.append(f"Estilo: {style}")
    if data.get("budget_eur") is not None:
        lines.append(f"Presupuesto: {data['budget_eur']:.0f} €")
    parts = [(data.get("description") or "").strip(), "\n".join(lines)]
    return "\n\n".join(p for p in parts if p)


def _assets(assets: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[Move]]:
    upgraded, moves = [], []
    for asset in assets:
        if (kind := asset.get("kind")) in _V1_FOLDERS:
            name = asset["stored_name"]
            moves.append((f"{_V1_FOLDERS[kind]}/{name}", f"{REFERENCE_FOLDER}/{name}"))
            asset = asset | {"kind": "referencia", "legacy_kind": kind}
        upgraded.append(asset)
    return upgraded, moves


def _render(render: dict[str, Any]) -> dict[str, Any]:
    if render.get("status") in {"descartado", "rechazado"}:
        return render | {"status": "generado"}
    return render


def upgrade_v1(data: dict[str, Any]) -> tuple[dict[str, Any], list[Move]]:
    """Convierte el contenido de un `metadatos.json` v1 en v2 (sin tocar el disco). Devuelve
    también los archivos que hay que mover."""
    upgraded = {k: v for k, v in data.items() if k not in _V1_PROJECT_FIELDS}
    upgraded["description"] = _description(data)
    upgraded["assets"], moves = _assets(data.get("assets", []))
    upgraded["renders"] = [_render(r) for r in data.get("renders", [])]
    upgraded["schema_version"] = SCHEMA_VERSION
    return upgraded, moves


def _move(root: Path, source: str, target: str) -> None:
    """Renombra sin sobrescribir; si el origen ya no está, una ejecución anterior lo movió."""
    origin, destination = root / source, root / target
    if not origin.exists():
        return
    if destination.exists():
        logger.warning("%s: %s ya existe, se deja %s en su sitio", root.name, target, source)
        return
    destination.parent.mkdir(exist_ok=True)
    replace_with_retry(origin, destination)


def _remove_empty_folders(root: Path) -> None:
    for folder in _V1_FOLDERS.values():
        path = root / folder
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def migrate(root: Path) -> bool:
    """Migra el proyecto de `root` si está en la v1. Devuelve si migró."""
    path = root / METADATA_FILE
    try:
        raw = path.read_bytes()
        data = json.loads(raw)
    except (OSError, ValueError):
        return False  # lo notificará la lectura normal (no existe o está corrupto)
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        return False
    backup = root / BACKUP_FILE
    if not backup.exists():  # si ya existe, un arranque anterior se cortó: se conserva
        write_bytes_atomic(backup, raw)
    upgraded, moves = upgrade_v1(data)
    metadata = ProjectMetadata.model_validate(upgraded)
    for source, target in moves:
        _move(root, source, target)
    write_json_atomic(path, metadata)
    _remove_empty_folders(root)
    logger.info(
        "Proyecto %s migrado al esquema v%d (original: %s)", root.name, SCHEMA_VERSION, BACKUP_FILE
    )
    return True
