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

from app.storage import migrations, telemetry_log, trash
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
    RenderRecord,
    TelemetryLog,
    TelemetryRecord,
    utc_now,
)

logger = logging.getLogger("interiorai.storage")

T = TypeVar("T")


class ProjectNotFoundError(LookupError):
    pass


class AssetNotFoundError(LookupError):
    pass


TRASH_KEY = "papelera"  # bloqueo de las operaciones sobre la papelera


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
        for project_id in on_disk:
            async with self._locks.hold(str(project_id)):
                await self._run(self._migrate_sync, project_id)
        async with self._locks.hold(INDEX_KEY):
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

    def _migrate_sync(self, project_id: UUID) -> None:
        """Pone al día un proyecto: esquema de `metadatos.json` (Paso 17) y telemetría en
        JSONL (B-012). Un proyecto que no se puede migrar se registra y se deja como está."""
        root = self._paths(project_id).root
        try:
            migrations.migrate(root)
        except (OSError, ValueError) as exc:
            logger.error("Proyecto %s sin migrar: %s", project_id, exc)
        telemetry_log.migrate(root)

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
        logger.info("Proyecto creado: %s", metadata.id)
        return metadata

    def _create_sync(self, metadata: ProjectMetadata) -> None:
        paths = self._paths(metadata.id)
        paths.root.mkdir()
        for kind in AssetKind:
            paths.folder(kind).mkdir()
        telemetry_log.create(paths.root)
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
        description: str = "",
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
            description=description.strip(),
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

    async def read_asset_bytes(self, project_id: str | UUID, asset_id: str | UUID) -> bytes:
        path = await self.asset_path(project_id, asset_id)
        return await self._run(path.read_bytes)

    def render_file_path(self, project_id: str | UUID, name: str) -> Path:
        """Ruta de un archivo auxiliar de un render en `renders_historico/` (p. ej. su máscara)."""
        return self._paths(project_id).asset(AssetKind.RENDER, name)

    async def read_render_file(self, project_id: str | UUID, name: str) -> bytes:
        return await self._run(self.render_file_path(project_id, name).read_bytes)

    async def mutate(
        self,
        project_id: str | UUID,
        change: Callable[[ProjectMetadata], tuple[ProjectMetadata, T]],
    ) -> T:
        """Lee, modifica y guarda `metadatos.json` bajo el bloqueo del proyecto.

        `change` recibe los metadatos actuales y devuelve (nuevos metadatos, resultado); puede
        lanzar excepciones para abortar sin escribir nada. `updated_at` se actualiza solo.
        """
        paths = self._paths(project_id)
        async with self._locks.hold(str(paths.project_id)):
            current = await self._run(self._read_metadata, paths)
            updated, result = change(current)
            updated = ProjectMetadata.model_validate(
                updated.model_dump() | {"updated_at": utc_now()}
            )
            await self._run(write_json_atomic, paths.metadata, updated)
            async with self._locks.hold(INDEX_KEY):
                await self._run(self._upsert_index, updated.summary())
        return result

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
            stamp = _trash_stamp()
            target = trash / f"{stamp}-{asset.stored_name}"
            await self._run(self._move_to_trash, paths.asset(asset.kind, asset.stored_name), target)
            if asset.kind is AssetKind.RENDER:  # su JSON (y archivos del retoque) van con ella
                record = next((r for r in metadata.renders if r.id == asset_uuid), None)
                sidecars = [f"{asset.id}.json"]
                if record is not None and record.inpaint is not None:
                    sidecars += record.inpaint.files
                for name in sidecars:
                    await self._run(
                        self._move_to_trash,
                        paths.asset(asset.kind, name),
                        trash / f"{stamp}-{name}",
                    )
            updated = metadata.model_copy(
                update={
                    "assets": [a for a in metadata.assets if a.id != asset_uuid],
                    "renders": [r for r in metadata.renders if r.id != asset_uuid],
                    "updated_at": utc_now(),
                }
            )
            await self._run(write_json_atomic, paths.metadata, updated)
            async with self._locks.hold(INDEX_KEY):
                await self._run(self._upsert_index, updated.summary())
        return target

    async def add_render(
        self,
        project_id: str | UUID,
        record: RenderRecord,
        content: bytes,
        mime_type: str,
        width_px: int,
        height_px: int,
        sidecars: dict[str, bytes] | None = None,
    ) -> Asset:
        """Guarda un render: imagen y JSON de trazabilidad en `renders_historico/`, el asset
        y su `RenderRecord` en `metadatos.json` (todo bajo el bloqueo del proyecto).

        `sidecars` ({nombre: contenido}): archivos auxiliares junto a la imagen (p. ej. la
        máscara, la salida en bruto y la guía de un retoque).
        """
        paths = self._paths(project_id)
        ext = "jpeg" if mime_type == "image/jpeg" else "png"
        asset = Asset(
            id=record.id,
            kind=AssetKind.RENDER,
            stored_name=f"{record.id}.{ext}",
            original_name=f"{record.stage.value}-{record.id.hex[:8]}.{ext}",
            mime_type=mime_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            width_px=width_px,
            height_px=height_px,
            description=f"{record.stage.label} (brief v{record.brief_version})",
        )
        async with self._locks.hold(str(paths.project_id)):
            metadata = await self._run(self._read_metadata, paths)
            await self._run(
                write_bytes_atomic, paths.asset(AssetKind.RENDER, asset.stored_name), content
            )
            await self._run(
                write_json_atomic, paths.asset(AssetKind.RENDER, f"{record.id}.json"), record
            )
            for name, data in (sidecars or {}).items():
                await self._run(write_bytes_atomic, paths.asset(AssetKind.RENDER, name), data)
            updated = metadata.model_copy(
                update={
                    "assets": [*metadata.assets, asset],
                    "renders": [*metadata.renders, record],
                    "updated_at": utc_now(),
                }
            )
            await self._run(write_json_atomic, paths.metadata, updated)
            async with self._locks.hold(INDEX_KEY):
                await self._run(self._upsert_index, updated.summary())
        return asset

    @staticmethod
    def _move_to_trash(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            replace_with_retry(source, target)

    # --- Telemetría ------------------------------------------------------------------

    def _read_telemetry_sync(self, paths: ProjectPaths) -> TelemetryLog:
        self._read_metadata(paths)  # 404 si el proyecto no existe
        return TelemetryLog(records=telemetry_log.read(paths.root))

    # --- Papelera ---------------------------------------------------------------------

    @property
    def trash_dir(self) -> Path:
        return self.data_dir / TRASH_DIR

    async def list_trash(self) -> tuple[list[trash.TrashedProject], list[trash.TrashedFile]]:
        return await self._run(trash.scan, self.trash_dir)

    async def restore_project(self, entry: str) -> ProjectMetadata:
        """Devuelve un proyecto borrado a `data/` y al índice."""
        async with self._locks.hold(TRASH_KEY):
            project_id = await self._run(
                trash.restore_project, self.trash_dir, self.data_dir, entry
            )
        async with self._locks.hold(str(project_id)):  # pudo borrarse con un esquema anterior
            await self._run(self._migrate_sync, project_id)
        metadata = await self.get(project_id)
        async with self._locks.hold(INDEX_KEY):
            await self._run(self._upsert_index, metadata.summary())
        logger.info("Proyecto %s restaurado desde la papelera", project_id)
        return metadata

    async def empty_trash(
        self, projects: list[trash.TrashedProject], files: list[trash.TrashedFile]
    ) -> int:
        """Borrado **definitivo** de lo seleccionado (la CLI pide confirmación antes)."""
        async with self._locks.hold(TRASH_KEY):
            freed = await self._run(trash.empty, self.trash_dir, projects, files)
        logger.info("Papelera: %d proyecto(s) y %d archivo(s) borrados", len(projects), len(files))
        return freed

    async def read_telemetry(self, project_id: str | UUID) -> TelemetryLog:
        paths = self._paths(project_id)
        async with self._locks.hold(str(paths.project_id)):
            return await self._run(self._read_telemetry_sync, paths)

    async def append_telemetry(self, project_id: str | UUID, record: TelemetryRecord) -> None:
        paths = self._paths(project_id)
        async with self._locks.hold(str(paths.project_id)):
            await self._run(self._read_metadata, paths)  # 404 si el proyecto no existe
            await self._run(telemetry_log.append, paths.root, record)
