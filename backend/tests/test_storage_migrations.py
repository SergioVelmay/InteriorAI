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
    data, _ = upgrade_v1(
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
    assert upgrade_v1(v1(description="Cocina.", space_type="cocina"))[0]["description"] == (
        "Cocina.\n\nTipo de espacio: Cocina"
    )
    assert upgrade_v1(v1(design_notes="Isla"))[0]["description"] == (
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


# --- B-048: sin rechazos ni descartes ---------------------------------------------------------


def test_rejected_and_discarded_renders_become_generated() -> None:
    renders = [
        {"id": "a", "status": "descartado"},
        {"id": "b", "status": "rechazado", "feedback": "Más luz"},
        {"id": "c", "status": "generado"},
    ]
    data, _ = upgrade_v1(v1(renders=renders))
    assert [r["status"] for r in data["renders"]] == ["generado"] * 3
    assert data["renders"][1]["feedback"] == "Más luz"  # se conserva como historia


# --- B-028: un solo tipo de imagen -----------------------------------------------------------


def v1_asset(kind: str, name: str) -> dict:
    return {
        "id": name.split(".")[0], "kind": kind, "stored_name": name, "original_name": name,
        "mime_type": "image/png", "size_bytes": 3, "sha256": "0" * 64, "description": "",
        "analysis": None, "created_at": "2026-10-18T07:40:00Z",
    }  # fmt: skip


async def test_captures_and_plans_become_references(repo: ProjectRepository) -> None:
    project = await repo.create(ProjectCreate(name="Cocina"))
    root = repo.data_dir / str(project.id)
    capture, plan, reference = (
        v1_asset("captura_sketchup", "0e8a6d5e-8d0c-4c51-9a55-0d6f3e6a1a01.png"),
        v1_asset("plano", "0e8a6d5e-8d0c-4c51-9a55-0d6f3e6a1a02.png"),
        v1_asset("referencia", "0e8a6d5e-8d0c-4c51-9a55-0d6f3e6a1a03.png"),
    )
    for folder, asset in (("capturas_sketchup", capture), ("planos", plan)):
        (root / folder).mkdir()
        (root / folder / asset["stored_name"]).write_bytes(b"png")
    (root / "referencias" / reference["stored_name"]).write_bytes(b"ref")
    write_v1(root, assets=[capture, plan, reference])

    assert migrate(root) is True
    migrated = await repo.get(project.id)
    assert [(a.kind.value, a.legacy_kind) for a in migrated.assets] == [
        ("referencia", "captura_sketchup"),
        ("referencia", "plano"),
        ("referencia", None),
    ]
    for asset in migrated.assets:
        assert (await repo.asset_path(project.id, asset.id)).read_bytes() in {b"png", b"ref"}
    assert not (root / "capturas_sketchup").exists() and not (root / "planos").exists()


async def test_interrupted_file_moves_are_completed(repo: ProjectRepository) -> None:
    project = await repo.create(ProjectCreate(name="Cocina"))
    root = repo.data_dir / str(project.id)
    capture = v1_asset("captura_sketchup", "0e8a6d5e-8d0c-4c51-9a55-0d6f3e6a1a01.png")
    (root / "capturas_sketchup").mkdir()
    (root / "referencias" / capture["stored_name"]).write_bytes(b"png")  # ya movida
    write_v1(root, assets=[capture])

    assert migrate(root) is True
    assert (await repo.read_asset_bytes(project.id, capture["id"])) == b"png"
