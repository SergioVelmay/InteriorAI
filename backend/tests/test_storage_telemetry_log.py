"""Telemetría en JSONL (B-012): añadir sin reescribir, migración y líneas cortadas."""

import json
from pathlib import Path

import pytest

from app.storage import ProjectRepository
from app.storage.telemetry_log import LEGACY_TELEMETRY_FILE, TELEMETRY_FILE
from shared.models import ProjectCreate, TelemetryRecord
from shared.roles import Role


def record(cost: float) -> TelemetryRecord:
    return TelemetryRecord(
        role=Role.FAST_DRAFT, deployment="d", operation="generate_image", status="ok",
        latency_s=1.0, cost_eur=cost,
    )  # fmt: skip


@pytest.fixture
async def repo(tmp_path: Path) -> ProjectRepository:
    repository = ProjectRepository(tmp_path / "data")
    await repository.init()
    return repository


async def new_project(repo: ProjectRepository) -> Path:
    project = await repo.create(ProjectCreate(name="x"))
    return repo.data_dir / str(project.id)


async def test_append_adds_one_line_per_call(repo: ProjectRepository) -> None:
    root = await new_project(repo)
    project_id = root.name
    for cost in (0.1, 0.2, 0.3):
        await repo.append_telemetry(project_id, record(cost))
    lines = (root / TELEMETRY_FILE).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3 and json.loads(lines[1])["cost_eur"] == 0.2
    log = await repo.read_telemetry(project_id)
    assert [r.cost_eur for r in log.records] == [0.1, 0.2, 0.3]


async def test_truncated_last_line_is_ignored_and_not_glued(repo: ProjectRepository) -> None:
    root = await new_project(repo)
    await repo.append_telemetry(root.name, record(0.1))
    path = root / TELEMETRY_FILE
    path.write_bytes(path.read_bytes() + b'{"role": "FAST_DR')  # corte a mitad de escritura
    assert [r.cost_eur for r in (await repo.read_telemetry(root.name)).records] == [0.1]
    await repo.append_telemetry(root.name, record(0.2))
    assert [r.cost_eur for r in (await repo.read_telemetry(root.name)).records] == [0.1, 0.2]


def legacy(root: Path, costs: list[float]) -> None:
    (root / TELEMETRY_FILE).unlink()
    log = {"schema_version": 1, "records": [record(c).model_dump(mode="json") for c in costs]}
    (root / LEGACY_TELEMETRY_FILE).write_text(json.dumps(log), encoding="utf-8")


async def test_legacy_file_is_migrated_on_startup_and_kept(tmp_path: Path) -> None:
    repo = ProjectRepository(tmp_path / "data")
    await repo.init()
    root = await new_project(repo)
    legacy(root, [0.1, 0.2])

    await ProjectRepository(tmp_path / "data").init()  # arranque del backend
    assert not (root / LEGACY_TELEMETRY_FILE).exists()
    assert (root / f"{LEGACY_TELEMETRY_FILE}.migrado").is_file()  # nunca se borra
    assert len((root / TELEMETRY_FILE).read_text(encoding="utf-8").splitlines()) == 2
    assert [r.cost_eur for r in (await repo.read_telemetry(root.name)).records] == [0.1, 0.2]


async def test_legacy_file_is_migrated_on_use(repo: ProjectRepository) -> None:
    """P. ej. un proyecto antiguo restaurado de la papelera después del arranque."""
    root = await new_project(repo)
    legacy(root, [0.5])
    await repo.append_telemetry(root.name, record(0.6))
    assert [r.cost_eur for r in (await repo.read_telemetry(root.name)).records] == [0.5, 0.6]


async def test_interrupted_migration_is_completed(repo: ProjectRepository) -> None:
    """El .jsonl ya se escribió pero no se renombró el .json: no se duplican registros."""
    root = await new_project(repo)
    legacy(root, [0.1])
    (root / TELEMETRY_FILE).write_bytes(record(0.1).model_dump_json().encode() + b"\n")
    assert len((await repo.read_telemetry(root.name)).records) == 1
    assert (root / f"{LEGACY_TELEMETRY_FILE}.migrado").is_file()
