"""Migración v2 → v3 (Paso 33, B-056): sin la compatibilidad con la v1."""

import json
import logging
from pathlib import Path

import pytest

from app.storage import CorruptDataError, ProjectRepository
from app.storage.migrations import BACKUP_FILE, migrate, upgrade_v2
from shared.models import ProjectCreate

PROJECT = "3fe26d9a-e294-44c2-95a8-25c2ecfef2d1"
DRAFT, RETOUCH, RAW, V2_RETOUCH = (f"0e8a6d5e-8d0c-4c51-9a55-0d6f3e6a1a0{i}" for i in range(1, 5))
CAPTURE, REFERENCE = (f"1e8a6d5e-8d0c-4c51-9a55-0d6f3e6a1a0{i}" for i in range(1, 3))
BRIEF = "2e8a6d5e-8d0c-4c51-9a55-0d6f3e6a1a01"


def asset(id: str, **extra: object) -> dict:
    return {
        "id": id, "kind": "referencia", "stored_name": f"{id}.png", "original_name": "x.png",
        "mime_type": "image/png", "size_bytes": 3, "sha256": "0" * 64, "description": "",
        "created_at": "2026-10-18T07:40:00Z",
    } | extra  # fmt: skip


def render(id: str, **extra: object) -> dict:
    return {
        "id": id, "stage": "composicion", "status": "generado", "role": "COMPOSITION_BUILDER",
        "deployment": "dep", "prompt": "p", "input_asset_ids": [CAPTURE],
        "batch_id": "4e8a6d5e-8d0c-4c51-9a55-0d6f3e6a1a01", "size": "1536x1024",
        "created_at": "2026-10-18T10:00:00Z",
    } | extra  # fmt: skip


def audit(**extra: object) -> dict:
    report = {"verdict": "conforme", "score": 90, "checks": [], "deviations": [],
              "suggested_prompt_adjustments": "", "summary": "Bien"}  # fmt: skip
    return {"report": report, "deployment": "dep", "reasoning_effort": "medium",
            "prompt_version": "auditor@x"} | extra  # fmt: skip


def v2(**fields: object) -> dict:
    """`metadatos.json` v2 con restos de la v1, como los proyectos de prueba del usuario."""
    return {
        "schema_version": 2, "id": PROJECT, "name": "Salón", "description": "",
        "created_at": "2026-10-18T07:38:32Z", "updated_at": "2026-10-24T09:39:06Z",
        "assets": [
            asset(CAPTURE, legacy_kind="captura_sketchup", analysis=None),
            asset(REFERENCE, analysis={"result": {}, "status": "proposed"}),
        ],
        "briefs": [{"id": BRIEF, "version": 1}],
        "renders": [
            render(DRAFT, stage="boceto", role="FAST_DRAFT_MAKER", brief_id=BRIEF,
                   brief_version=1, feedback="Más luz", status="seleccionado",
                   audits=[audit(reference_asset_id=CAPTURE)]),
            render(RETOUCH, brief_id=BRIEF, brief_version=1, parent_render_id=DRAFT,
                   inpaint={"source_render_id": DRAFT, "instruction": "planta",
                            "mask_file": "m.png", "raw_file": "r.png", "guide_file": None,
                            "coverage": 0.1, "feather_px": 12, "method": "mascara"}),
            render(RAW, raw_of_render_id=RETOUCH, previous_attempt_id=DRAFT),
            render(V2_RETOUCH, parent_render_id=DRAFT,
                   prompt_info={"prompt": "p", "interpretation": "i", "open_questions": []},
                   inpaint={"source_render_id": DRAFT, "instruction": "frigorífico",
                            "mask_file": "m2.png", "coverage": 0.2, "method": "mascara"}),
        ],
    } | fields  # fmt: skip


def write_v2(root: Path, **fields: object) -> dict:
    data = v2(**{"id": root.name, **fields})
    (root / "metadatos.json").write_text(json.dumps(data), encoding="utf-8")
    return data


@pytest.fixture
async def repo(tmp_path: Path) -> ProjectRepository:
    repository = ProjectRepository(tmp_path / "data")
    await repository.init()
    return repository


def test_v1_images_stay_as_loose_images() -> None:
    """Decisión del usuario (2026-10-27): las imágenes de la v1 se conservan sin su cadena."""
    data = upgrade_v2(v2())
    assert data["schema_version"] == 3 and "briefs" not in data
    renders = {r["id"]: r for r in data["renders"]}
    for id in (DRAFT, RETOUCH, RAW):  # sin brief, rechazo, intento anterior ni salida en bruto
        assert not {"brief_id", "brief_version", "feedback", "previous_attempt_id",
                    "raw_of_render_id"} & set(renders[id])  # fmt: skip
    assert renders[DRAFT]["status"] == "seleccionado"  # la selección no cambia
    assert "inpaint" not in renders[RETOUCH]  # retoque recompuesto de la v1: imagen suelta
    assert renders[RETOUCH]["parent_render_id"] == DRAFT
    assert renders[V2_RETOUCH]["inpaint"] == {  # retoque con máscara nativa (v2): se conserva
        "source_render_id": DRAFT, "instruction": "frigorífico", "mask_file": "m2.png",
        "coverage": 0.2,
    }  # fmt: skip
    assert renders[DRAFT]["audits"][0].keys() >= {"report", "deployment"}
    assert "reference_asset_id" not in renders[DRAFT]["audits"][0]


def test_references_lose_the_v1_sheet_and_kind() -> None:
    assets = upgrade_v2(v2())["assets"]
    assert all(not {"analysis", "legacy_kind"} & set(a) for a in assets)
    assert [a["id"] for a in assets] == [CAPTURE, REFERENCE]


async def test_migrate_backs_up_and_is_repeatable(repo: ProjectRepository) -> None:
    project = await repo.create(ProjectCreate(name="Salón"))
    root = repo.data_dir / str(project.id)
    original = write_v2(root)

    assert migrate(root) is True
    assert json.loads((root / BACKUP_FILE).read_text(encoding="utf-8")) == original
    migrated = await repo.get(project.id)
    assert migrated.schema_version == 3 and len(migrated.renders) == 4
    assert migrate(root) is False  # ya está en la v3


async def test_migrate_keeps_first_backup_after_interrupted_run(repo: ProjectRepository) -> None:
    project = await repo.create(ProjectCreate(name="Salón"))
    root = repo.data_dir / str(project.id)
    original = write_v2(root)
    (root / BACKUP_FILE).write_text(json.dumps(original), encoding="utf-8")
    write_v2(root, name="Otro")  # p. ej. el usuario lo editó a mano después del corte

    assert migrate(root) is True
    assert json.loads((root / BACKUP_FILE).read_text(encoding="utf-8")) == original


def test_migrate_ignores_missing_or_corrupt_metadata(tmp_path: Path) -> None:
    assert migrate(tmp_path) is False
    (tmp_path / "metadatos.json").write_text("{roto", encoding="utf-8")
    assert migrate(tmp_path) is False


async def test_init_migrates_projects(repo: ProjectRepository) -> None:
    project = await repo.create(ProjectCreate(name="Salón"))
    write_v2(repo.data_dir / str(project.id), name="Salón de pruebas")

    fresh = ProjectRepository(repo.data_dir)
    await fresh.init()
    assert (await fresh.get(project.id)).name == "Salón de pruebas"
    assert [p.id for p in await fresh.list_projects()] == [project.id]


async def test_restored_v2_project_is_migrated(repo: ProjectRepository) -> None:
    project = await repo.create(ProjectCreate(name="Salón"))
    trashed = await repo.delete(project.id)
    write_v2(trashed, id=str(project.id), name="Salón antiguo")

    restored = await repo.restore_project(trashed.name)
    assert restored.name == "Salón antiguo" and restored.schema_version == 3
    assert (repo.data_dir / str(project.id) / BACKUP_FILE).is_file()


async def test_data_from_1_0_0_is_no_longer_read(
    repo: ProjectRepository, caplog: pytest.LogCaptureFixture
) -> None:
    """Decisión del usuario (2026-10-27): quien venga de la 1.0.0 actualiza antes a la 3.0.0."""
    project = await repo.create(ProjectCreate(name="Salón"))
    root = repo.data_dir / str(project.id)
    (root / "metadatos.json").write_text(json.dumps(v2(schema_version=1)), encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="interiorai.storage"):
        assert migrate(root) is False
    assert "versión 3.0.0" in caplog.text
    with pytest.raises(CorruptDataError):
        await repo.get(project.id)
