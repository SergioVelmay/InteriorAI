"""Papelera (`data/.papelera/`): listar, restaurar proyectos y vaciar (B-007).

Contenido que dejan los borrados suaves de `ProjectRepository`:

- Proyecto borrado: carpeta completa `{id}-{marca}` (con su `metadatos.json`).
- Asset borrado: `{id}/{marca}-{archivo}` (y los archivos auxiliares de un render).

Solo se restauran proyectos completos: un asset borrado ya no figura en `metadatos.json`.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

STAMP_FORMAT = "%Y%m%dT%H%M%S%fZ"
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
PROJECT_ENTRY = re.compile(rf"^(?P<id>{_UUID})-(?P<stamp>\d{{8}}T\d{{12}}Z)$")
ASSET_DIR = re.compile(rf"^(?P<id>{_UUID})$")
ASSET_FILE = re.compile(r"^(?P<stamp>\d{8}T\d{12}Z)-.+$")


class TrashError(Exception):
    pass


@dataclass(frozen=True)
class TrashedProject:
    entry: str  # nombre de la carpeta en la papelera (lo que se pasa a «restaurar»)
    project_id: UUID
    name: str | None
    deleted_at: datetime
    size_bytes: int


@dataclass(frozen=True)
class TrashedFile:
    project_id: UUID
    path: Path
    deleted_at: datetime
    size_bytes: int


def _stamp(value: str) -> datetime:
    return datetime.strptime(value, STAMP_FORMAT).replace(tzinfo=UTC)


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())


def _name(folder: Path) -> str | None:
    """Nombre del proyecto, sea cual sea su esquema (pudo borrarse con una versión anterior)."""
    try:
        name = json.loads((folder / "metadatos.json").read_text(encoding="utf-8")).get("name")
    except (OSError, ValueError, AttributeError):
        return None
    return name if isinstance(name, str) else None


def scan(trash: Path) -> tuple[list[TrashedProject], list[TrashedFile]]:
    """Contenido reconocido de la papelera (lo demás se ignora y nunca se borra)."""
    projects: list[TrashedProject] = []
    files: list[TrashedFile] = []
    if not trash.is_dir():
        return projects, files
    for item in sorted(trash.iterdir()):
        if item.is_symlink() or not item.is_dir():
            continue
        if match := PROJECT_ENTRY.match(item.name):
            projects.append(TrashedProject(
                entry=item.name, project_id=UUID(match["id"]), name=_name(item),
                deleted_at=_stamp(match["stamp"]), size_bytes=_size(item),
            ))  # fmt: skip
        elif match := ASSET_DIR.match(item.name):
            for file in sorted(item.iterdir()):
                stamp = ASSET_FILE.match(file.name)
                if stamp and file.is_file() and not file.is_symlink():
                    files.append(TrashedFile(
                        project_id=UUID(match["id"]), path=file,
                        deleted_at=_stamp(stamp["stamp"]), size_bytes=file.stat().st_size,
                    ))  # fmt: skip
    return projects, files


def restore_project(trash: Path, data_dir: Path, entry: str) -> UUID:
    """Devuelve la carpeta del proyecto a `data/` (el índice lo actualiza el repositorio)."""
    match = PROJECT_ENTRY.match(entry)
    source = trash / entry
    if match is None or not source.is_dir() or source.is_symlink():
        raise TrashError(f"No hay ningún proyecto «{entry}» en la papelera")
    target = data_dir / match["id"]
    if target.exists():
        raise TrashError(f"Ya existe un proyecto con el id {match['id']}: no se sobrescribe")
    source.replace(target)
    return UUID(match["id"])


def selection(
    trash: Path, older_than: timedelta | None, now: datetime | None = None
) -> tuple[list[TrashedProject], list[TrashedFile]]:
    projects, files = scan(trash)
    if older_than is None:
        return projects, files
    limit = (now or datetime.now(UTC)) - older_than
    return (
        [p for p in projects if p.deleted_at < limit],
        [f for f in files if f.deleted_at < limit],
    )


def empty(trash: Path, projects: list[TrashedProject], files: list[TrashedFile]) -> int:
    """Borra de forma definitiva lo seleccionado. Devuelve los bytes liberados."""
    freed = 0
    for project in projects:
        folder = trash / project.entry
        freed += project.size_bytes
        shutil.rmtree(folder)
    for file in files:
        freed += file.size_bytes
        file.path.unlink()
    for folder in trash.iterdir():  # carpetas de assets que quedan vacías
        if ASSET_DIR.match(folder.name) and folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    return freed
