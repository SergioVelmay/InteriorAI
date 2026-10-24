import json
from pathlib import Path

import pytest

from app.storage import ProjectRepository
from app.storage.migrations import BACKUP_FILE, migrate, upgrade_v1
from shared.models import ProjectCreate


def v1(**fields: object) -> dict:
    """`metadatos.json` mínimo de la v1."""
    return {
        "schema_version": 1,
        "id": "3fe26d9a-e294-44c2-95a8-25c2ecfef2d1",
        "name": "Salón",
        "space_type": "salon_cocina_comedor",
        "description": "",
        "design_notes": "",
        "dimensions": None,
        "style": "",
        "budget_eur": None,
        "created_at": "2026-10-18T07:38:32.874948Z",
        "updated_at": "2026-10-24T09:39:06.430177Z",
        "assets": [],
        "briefs": [],
        "renders": [],
    } | fields


def write_v1(root: Path, **fields: object) -> dict:
    data = v1(**{"id": root.name, **fields})
    (root / "metadatos.json").write_text(json.dumps(data), encoding="utf-8")
    return data


@pytest.fixture
async def repo(tmp_path: Path) -> ProjectRepository:
    repository = ProjectRepository(tmp_path / "data")
    await repository.init()
    return repository


# --- B-026: campos del proyecto --------------------------------------------------------------


def test_description_keeps_removed_fields_with_value() -> None:
    data = upgrade_v1(
        v1(
            description="Salón de 25 m².",
            design_notes="Sofá en L.\nTonos verdes.",
            dimensions={"width_m": 4.5, "length_m": 6, "height_m": 2.6},
            style="nórdico",
            budget_eur=3000,
        )
    )
    assert data["description"] == (
        "Salón de 25 m².\n\n"
        "Tipo de espacio: Salón-cocina-comedor\n"
        "Notas de diseño: Sofá en L.\nTonos verdes.\n"
        "Dimensiones: 4,5 x 6 m x 2,6 m de alto\n"
        "Estilo: nórdico\n"
        "Presupuesto: 3000 €"
    )
    assert data["schema_version"] == 2
    assert not {"space_type", "design_notes", "dimensions", "style", "budget_eur"} & set(data)


def test_description_only_adds_fields_with_value() -> None:
    assert upgrade_v1(v1(description="Cocina.", space_type="cocina"))["description"] == (
        "Cocina.\n\nTipo de espacio: Cocina"
    )
    assert upgrade_v1(v1(design_notes="Isla"))["description"] == (
        "Tipo de espacio: Salón-cocina-comedor\nNotas de diseño: Isla"
    )


# --- Migración en disco -----------------------------------------------------------------------


async def test_migrate_backs_up_and_is_repeatable(repo: ProjectRepository) -> None:
    project = await repo.create(ProjectCreate(name="Salón"))
    root = repo.data_dir / str(project.id)
    original = write_v1(root, description="Salón.")

    assert migrate(root) is True
    assert json.loads((root / BACKUP_FILE).read_text(encoding="utf-8")) == original
    migrated = json.loads((root / "metadatos.json").read_text(encoding="utf-8"))
    assert migrated["schema_version"] == 2
    assert migrated["description"] == "Salón.\n\nTipo de espacio: Salón-cocina-comedor"
    assert migrate(root) is False  # ya está en la v2


async def test_migrate_keeps_first_backup_after_interrupted_run(repo: ProjectRepository) -> None:
    project = await repo.create(ProjectCreate(name="Salón"))
    root = repo.data_dir / str(project.id)
    original = write_v1(root)
    (root / BACKUP_FILE).write_text(json.dumps(original), encoding="utf-8")
    write_v1(root, name="Otro")  # p. ej. el usuario lo editó a mano después del corte

    assert migrate(root) is True
    assert json.loads((root / BACKUP_FILE).read_text(encoding="utf-8")) == original


def test_migrate_ignores_missing_or_corrupt_metadata(tmp_path: Path) -> None:
    assert migrate(tmp_path) is False
    (tmp_path / "metadatos.json").write_text("{roto", encoding="utf-8")
    assert migrate(tmp_path) is False


async def test_init_migrates_projects_and_rebuilds_v1_index(repo: ProjectRepository) -> None:
    project = await repo.create(ProjectCreate(name="Salón"))
    root = repo.data_dir / str(project.id)
    write_v1(root, design_notes="Sofá")
    summary = {"id": str(project.id), "name": "Salón", "space_type": "salon"}
    times = {"created_at": "2026-10-18T07:38:32Z", "updated_at": "2026-10-18T07:38:32Z"}
    repo.index_path.write_text(
        json.dumps({"schema_version": 1, "projects": [summary | times]}), encoding="utf-8"
    )

    fresh = ProjectRepository(repo.data_dir)
    await fresh.init()
    assert (await fresh.get(project.id)).description.endswith("Notas de diseño: Sofá")
    assert [p.id for p in await fresh.list_projects()] == [project.id]
    assert json.loads(fresh.index_path.read_text(encoding="utf-8"))["schema_version"] == 2


async def test_restored_v1_project_is_migrated(repo: ProjectRepository) -> None:
    project = await repo.create(ProjectCreate(name="Salón"))
    trashed = await repo.delete(project.id)
    write_v1(trashed, id=str(project.id), name="Salón antiguo")

    projects, _ = await repo.list_trash()
    assert [p.name for p in projects] == ["Salón antiguo"]  # nombre legible en la v1
    restored = await repo.restore_project(trashed.name)
    assert restored.name == "Salón antiguo"
    assert (repo.data_dir / str(project.id) / BACKUP_FILE).is_file()
