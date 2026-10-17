"""Rutas seguras dentro de `DATA_DIR`.

Toda ruta se construye a partir de UUIDs validados y se comprueba que queda dentro del
directorio de datos. Los nombres de archivo del usuario nunca se usan en disco.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePath
from uuid import UUID

from shared.models import AssetKind

INDEX_FILE = "proyectos.json"
METADATA_FILE = "metadatos.json"
TELEMETRY_FILE = "costes_telemetria.json"
TRASH_DIR = ".papelera"
LOCKS_DIR = ".locks"

_SAFE_EXTENSION = re.compile(r"^[a-z0-9]{1,8}$")
_UNSAFE_NAME_CHARS = re.compile(r'[\x00-\x1f\x7f"]')


class InvalidPathError(ValueError):
    """Identificador o ruta fuera del directorio de datos."""


def parse_uuid(value: str | UUID) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise InvalidPathError(f"Identificador no válido: {value!r}") from exc


def safe_join(base: Path, *parts: str) -> Path:
    """Une `parts` a `base` garantizando que el resultado queda estrictamente dentro."""
    root = base.resolve()
    target = root.joinpath(*parts).resolve()
    if target == root or not target.is_relative_to(root):
        raise InvalidPathError("La ruta queda fuera del directorio de datos")
    return target


def stored_asset_name(asset_id: UUID, original_name: str) -> str:
    """Nombre en disco: `{uuid}.{ext}`; la extensión solo si es alfanumérica y corta."""
    suffix = PurePath(original_name.replace("\\", "/")).suffix.lower().lstrip(".")
    ext = suffix if _SAFE_EXTENSION.fullmatch(suffix) else "bin"
    return f"{asset_id}.{ext}"


def clean_original_name(original_name: str) -> str:
    """Nombre original para mostrar: sin directorios, controles ni comillas (va en cabeceras)."""
    name = PurePath(original_name.replace("\\", "/")).name
    name = _UNSAFE_NAME_CHARS.sub("_", name).strip()
    return name[:255] or "archivo"


class ProjectPaths:
    def __init__(self, data_dir: Path, project_id: str | UUID) -> None:
        self.project_id = parse_uuid(project_id)
        self.root = safe_join(data_dir, str(self.project_id))

    @property
    def metadata(self) -> Path:
        return self.root / METADATA_FILE

    @property
    def telemetry(self) -> Path:
        return self.root / TELEMETRY_FILE

    def folder(self, kind: AssetKind) -> Path:
        return self.root / kind.folder

    def asset(self, kind: AssetKind, stored_name: str) -> Path:
        return safe_join(self.root, kind.folder, stored_name)
