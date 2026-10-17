"""Repositorio de proyectos sobre el sistema de archivos.

Toda la E/S de disco se ejecuta en el pool de hilos (`anyio.to_thread`) bajo el bloqueo
del proyecto y, cuando cambia el índice, también bajo el del índice (en ese orden).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import TypeVar
from uuid import UUID, uuid4

import anyio

from app.storage.atomic import (
    CorruptDataError,
    read_json,
    replace_with_retry,
    write_bytes_atomic,
    write_json_atomic,
)
from app.storage.locks import INDEX_KEY, LockManager
from app.storage.paths import (
    INDEX_FILE,
    LOCKS_DIR,
    METADATA_FILE,
    TRASH_DIR,
    InvalidPathError,
    ProjectPaths,
    clean_original_name,
    parse_uuid,
    safe_join,
    stored_asset_name,
)
from shared.models import (
    Asset,
    AssetKind,
    ProjectCreate,
    ProjectIndex,
    ProjectMetadata,
    ProjectSummary,
    ProjectUpdate,
    TelemetryLog,
    utc_now,
)

logger = logging.getLogger("interiorai.storage")

T = TypeVar("T")


class ProjectNotFoundError(LookupError):
    pass


class AssetNotFoundError(LookupError):
    pass


def _trash_stamp() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%S%fZ")


class ProjectRepository:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self._locks = LockManager(data_dir / LOCKS_DIR)

    @property
    def index_path(self) -> Path:
        return self.data_dir / INDEX_FILE

    @staticmethod
    async def _run(func: Callable[..., T], *args: object) -> T:
        return await anyio.to_thread.run_sync(partial(func, *args))

    def _paths(self, project_id: str | UUID) -> ProjectPaths:
        return ProjectPaths(self.data_dir, project_id)

    # --- Arranque y consistencia ---------------------------------------------------

    async def init(self) -> None:
        """Prepara `DATA_DIR` y reconstruye el índice si falta, está corrupto o no coincide
        con las carpetas (el índice siempre es derivable de los `metadatos.json`)."""
        await self._run(self._init_dirs)
        async with self._locks.hold(INDEX_KEY):
            on_disk = set(await self._run(self._scan_project_ids))
            if not self.index_path.exists():
                reason = "no existe"
            else:
                try:
                    indexed = {p.id for p in await self._run(self._read_index)}
                    reason = "" if indexed == on_disk else "desincronizado"
                except CorruptDataError:
                    reason = "corrupto"
        if reason:
            logger.warning("Índice %s (%d proyectos en disco): reindexando", reason, len(on_disk))
            await self.reindex()

    def _init_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / LOCKS_DIR).mkdir(exist_ok=True)
        (self.data_dir / TRASH_DIR).mkdir(exist_ok=True)

    def _scan_project_ids(self) -> list[UUID]:
        ids = []
        for entry in self.data_dir.iterdir():
            if not entry.is_dir() or not (entry / METADATA_FILE).is_file():
                continue
            try:
                ids.append(parse_uuid(entry.name))
            except InvalidPathError:
                continue
        return ids

    async def reindex(self) -> int:
        """Reconstruye `proyectos.json` a partir de las carpetas. Devuelve nº de proyectos."""
        async with self._locks.hold(INDEX_KEY):
            return await self._run(self._reindex_sync)

    def _reindex_sync(self) -> int:
        summaries = []
        for project_id in self._scan_project_ids():
            try:
                metadata = read_json(self._paths(project_id).metadata, ProjectMetadata)
            except (CorruptDataError, OSError) as exc:
                logger.error("Proyecto %s omitido del índice: %s", project_id, exc)
                continue
            summaries.append(metadata.summary())
        index = ProjectIndex(projects=summaries)
        write_json_atomic(self.index_path, index)
        return len(index.projects)

    # --- Índice ----------------------------------------------------------------------

    def _read_index(self) -> list[ProjectSummary]:
        if not self.index_path.exists():
            return []
        return read_json(self.index_path, ProjectIndex).projects

    def _upsert_index(self, summary: ProjectSummary) -> None:
        projects = [p for p in self._read_index() if p.id != summary.id]
        projects.append(summary)
        write_json_atomic(self.index_path, ProjectIndex(projects=projects))

    def _remove_from_index(self, project_id: UUID) -> None:
        projects = [p for p in self._read_index() if p.id != project_id]
        write_json_atomic(self.index_path, ProjectIndex(projects=projects))

    # --- Proyectos -------------------------------------------------------------------

    async def list_projects(self) -> list[ProjectSummary]:
        async with self._locks.hold(INDEX_KEY):
            projects = await self._run(self._read_index)
        return sorted(projects, key=lambda p: p.updated_at, reverse=True)

    async def create(self, data: ProjectCreate) -> ProjectMetadata:
        now = utc_now()
        metadata = ProjectMetadata(**data.model_dump(), id=uuid4(), created_at=now, updated_at=now)
        key = str(metadata.id)
        async with self._locks.hold(key):
            await self._run(self._create_sync, metadata)
            async with self._locks.hold(INDEX_KEY):
                await self._run(self._upsert_index, metadata.summary())
        logger.info("Proyecto creado: %s (%s)", metadata.id, metadata.space_type.value)
        return metadata

    def _create_sync(self, metadata: ProjectMetadata) -> None:
        paths = self._paths(metadata.id)
        paths.root.mkdir()
        for kind in AssetKind:
            paths.folder(kind).mkdir()
        write_json_atomic(paths.telemetry, TelemetryLog())
        # metadatos.json en último lugar: su presencia marca el proyecto como completo.
        write_json_atomic(paths.metadata, metadata)

    def _read_metadata(self, paths: ProjectPaths) -> ProjectMetadata:
        if not paths.metadata.is_file():
            raise ProjectNotFoundError(str(paths.project_id))
        return read_json(paths.metadata, ProjectMetadata)

    async def get(self, project_id: str | UUID) -> ProjectMetadata:
        paths = self._paths(project_id)
        async with self._locks.hold(str(paths.project_id)):
            return await self._run(self._read_metadata, paths)

    async def update(self, project_id: str | UUID, changes: ProjectUpdate) -> ProjectMetadata:
        paths = self._paths(project_id)
        async with self._locks.hold(str(paths.project_id)):
            current = await self._run(self._read_metadata, paths)
            merged = current.model_dump() | changes.changes() | {"updated_at": utc_now()}
            updated = ProjectMetadata.model_validate(merged)
            await self._run(write_json_atomic, paths.metadata, updated)
            async with self._locks.hold(INDEX_KEY):
                await self._run(self._upsert_index, updated.summary())
        return updated

    async def delete(self, project_id: str | UUID) -> Path:
        """Borrado suave: mueve el proyecto a `.papelera/`. Devuelve la ruta destino."""
        paths = self._paths(project_id)
        async with self._locks.hold(str(paths.project_id)):
            await self._run(self._read_metadata, paths)
            target = self.data_dir / TRASH_DIR / f"{paths.project_id}-{_trash_stamp()}"
            await self._run(replace_with_retry, paths.root, target)
            async with self._locks.hold(INDEX_KEY):
                await self._run(self._remove_from_index, paths.project_id)
        logger.info("Proyecto %s movido a la papelera: %s", paths.project_id, target.name)
        return target

    # --- Assets ----------------------------------------------------------------------

    async def add_asset(
        self,
        project_id: str | UUID,
        kind: AssetKind,
        content: bytes,
        original_name: str,
        mime_type: str,
        width_px: int | None = None,
        height_px: int | None = None,
    ) -> Asset:
        paths = self._paths(project_id)
        asset_id = uuid4()
        asset = Asset(
            id=asset_id,
            kind=kind,
            stored_name=stored_asset_name(asset_id, original_name),
            original_name=clean_original_name(original_name),
            mime_type=mime_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            width_px=width_px,
            height_px=height_px,
        )
        async with self._locks.hold(str(paths.project_id)):
            metadata = await self._run(self._read_metadata, paths)
            await self._run(write_bytes_atomic, paths.asset(kind, asset.stored_name), content)
            updated = metadata.model_copy(
                update={"assets": [*metadata.assets, asset], "updated_at": asset.created_at}
            )
            await self._run(write_json_atomic, paths.metadata, updated)
            async with self._locks.hold(INDEX_KEY):
                await self._run(self._upsert_index, updated.summary())
        return asset

    async def list_assets(
        self, project_id: str | UUID, kind: AssetKind | None = None
    ) -> list[Asset]:
        metadata = await self.get(project_id)
        return [a for a in metadata.assets if kind is None or a.kind is kind]

    async def get_asset(self, project_id: str | UUID, asset_id: str | UUID) -> Asset:
        asset_uuid = parse_uuid(asset_id)
        for asset in await self.list_assets(project_id):
            if asset.id == asset_uuid:
                return asset
        raise AssetNotFoundError(str(asset_uuid))

    async def asset_path(self, project_id: str | UUID, asset_id: str | UUID) -> Path:
        asset = await self.get_asset(project_id, asset_id)
        return self._paths(project_id).asset(asset.kind, asset.stored_name)

    async def remove_asset(self, project_id: str | UUID, asset_id: str | UUID) -> Path:
        """Borrado suave: mueve el archivo a `.papelera/{proyecto}/`. Devuelve la ruta destino."""
        asset_uuid = parse_uuid(asset_id)
        paths = self._paths(project_id)
        async with self._locks.hold(str(paths.project_id)):
            metadata = await self._run(self._read_metadata, paths)
            asset = next((a for a in metadata.assets if a.id == asset_uuid), None)
            if asset is None:
                raise AssetNotFoundError(str(asset_uuid))
            trash = safe_join(self.data_dir, TRASH_DIR, str(paths.project_id))
            target = trash / f"{_trash_stamp()}-{asset.stored_name}"
            await self._run(self._move_to_trash, paths.asset(asset.kind, asset.stored_name), target)
            updated = metadata.model_copy(
                update={
                    "assets": [a for a in metadata.assets if a.id != asset_uuid],
                    "updated_at": utc_now(),
                }
            )
            await self._run(write_json_atomic, paths.metadata, updated)
            async with self._locks.hold(INDEX_KEY):
                await self._run(self._upsert_index, updated.summary())
        return target

    @staticmethod
    def _move_to_trash(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            replace_with_retry(source, target)
