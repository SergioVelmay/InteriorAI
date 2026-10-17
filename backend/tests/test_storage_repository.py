import asyncio
import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from app.storage import (
    AssetNotFoundError,
    InvalidPathError,
    ProjectNotFoundError,
    ProjectRepository,
)
from app.storage.__main__ import main as cli_main
from shared.models import AssetKind, ProjectCreate, ProjectUpdate, SpaceType

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture
async def repo(tmp_path: Path) -> ProjectRepository:
    repository = ProjectRepository(tmp_path / "data")
    await repository.init()
    return repository


def new_project(name: str = "Salón principal") -> ProjectCreate:
    return ProjectCreate(name=name, space_type=SpaceType.SALON_COCINA_COMEDOR)


def read_index(repo: ProjectRepository) -> dict:
    return json.loads(repo.index_path.read_text(encoding="utf-8"))


# --- Proyectos -------------------------------------------------------------------------


async def test_create_builds_full_structure(repo: ProjectRepository) -> None:
    project = await repo.create(new_project())
    root = repo.data_dir / str(project.id)
    for folder in ("planos", "referencias", "capturas_sketchup", "renders_historico"):
        assert (root / folder).is_dir()
    assert json.loads((root / "metadatos.json").read_text(encoding="utf-8"))["name"] == (
        "Salón principal"
    )
    assert json.loads((root / "costes_telemetria.json").read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "records": [],
    }
    index = read_index(repo)
    assert index["schema_version"] == 1
    assert [p["id"] for p in index["projects"]] == [str(project.id)]


async def test_get_list_update(repo: ProjectRepository) -> None:
    first = await repo.create(new_project("Primero"))
    second = await repo.create(new_project("Segundo"))
    assert (await repo.get(first.id)).name == "Primero"
    assert (await repo.get(str(first.id))).id == first.id

    updated = await repo.update(
        first.id, ProjectUpdate(name="Primero (editado)", design_notes="Tonos cálidos")
    )
    assert updated.name == "Primero (editado)"
    assert updated.design_notes == "Tonos cálidos"
    assert updated.space_type is SpaceType.SALON_COCINA_COMEDOR
    assert updated.updated_at > first.updated_at

    listed = await repo.list_projects()
    assert [p.id for p in listed] == [first.id, second.id]  # más reciente primero
    assert listed[0].name == "Primero (editado)"


async def test_update_rejects_null_required_field(repo: ProjectRepository) -> None:
    project = await repo.create(new_project())
    with pytest.raises(ValueError):
        await repo.update(project.id, ProjectUpdate(name=None))
    assert (await repo.get(project.id)).name == "Salón principal"


async def test_delete_moves_to_trash(repo: ProjectRepository) -> None:
    project = await repo.create(new_project())
    target = await repo.delete(project.id)
    assert not (repo.data_dir / str(project.id)).exists()
    assert target.parent == repo.data_dir / ".papelera"
    assert (target / "metadatos.json").is_file()
    assert await repo.list_projects() == []
    with pytest.raises(ProjectNotFoundError):
        await repo.get(project.id)


async def test_missing_and_invalid_ids(repo: ProjectRepository) -> None:
    with pytest.raises(ProjectNotFoundError):
        await repo.get(uuid4())
    with pytest.raises(InvalidPathError):
        await repo.get("../../etc")
    with pytest.raises(ProjectNotFoundError):
        await repo.delete(uuid4())


# --- Assets ----------------------------------------------------------------------------


async def test_add_list_and_resolve_asset(repo: ProjectRepository) -> None:
    project = await repo.create(new_project())
    asset = await repo.add_asset(
        project.id, AssetKind.PLANO, PNG, "../../Plano Salón.PNG", "image/png"
    )

    assert asset.original_name == "Plano Salón.PNG"
    assert asset.stored_name == f"{asset.id}.png"
    assert asset.size_bytes == len(PNG)
    assert len(asset.sha256) == 64

    path = await repo.asset_path(project.id, asset.id)
    assert path == repo.data_dir / str(project.id) / "planos" / asset.stored_name
    assert path.read_bytes() == PNG

    assert [a.id for a in await repo.list_assets(project.id)] == [asset.id]
    assert await repo.list_assets(project.id, AssetKind.REFERENCIA) == []


async def test_remove_asset_moves_file_to_trash(repo: ProjectRepository) -> None:
    project = await repo.create(new_project())
    asset = await repo.add_asset(project.id, AssetKind.REFERENCIA, PNG, "ikea.png", "image/png")
    target = await repo.remove_asset(project.id, asset.id)
    assert target.read_bytes() == PNG
    assert target.parent == repo.data_dir / ".papelera" / str(project.id)
    assert await repo.list_assets(project.id) == []
    with pytest.raises(AssetNotFoundError):
        await repo.asset_path(project.id, asset.id)


# --- Concurrencia ----------------------------------------------------------------------


async def test_concurrent_creates_keep_index_consistent(repo: ProjectRepository) -> None:
    created = await asyncio.gather(*(repo.create(new_project(f"P{i}")) for i in range(50)))
    index = read_index(repo)
    assert len(index["projects"]) == 50
    assert {p["id"] for p in index["projects"]} == {str(p.id) for p in created}


async def test_concurrent_assets_from_two_repositories(tmp_path: Path) -> None:
    """Dos instancias (como dos procesos) sobre el mismo DATA_DIR: actúa el filelock."""
    data_dir = tmp_path / "data"
    repo_a, repo_b = ProjectRepository(data_dir), ProjectRepository(data_dir)
    await repo_a.init()
    project = await repo_a.create(new_project())

    await asyncio.gather(
        *(
            (repo_a if i % 2 else repo_b).add_asset(
                project.id, AssetKind.REFERENCIA, PNG + bytes([i]), f"ref{i}.png", "image/png"
            )
            for i in range(30)
        )
    )
    assets = await repo_a.list_assets(project.id)
    assert len(assets) == 30
    assert len({a.sha256 for a in assets}) == 30


# --- Consistencia del índice -------------------------------------------------------------


async def test_reindex_rebuilds_from_folders(repo: ProjectRepository) -> None:
    projects = [await repo.create(new_project(f"P{i}")) for i in range(3)]
    repo.index_path.unlink()
    assert await repo.reindex() == 3
    assert {p["id"] for p in read_index(repo)["projects"]} == {str(p.id) for p in projects}


async def test_init_repairs_desynchronized_index(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    repo = ProjectRepository(data_dir)
    await repo.init()
    kept = await repo.create(new_project("Se queda"))
    gone = await repo.create(new_project("Borrado a mano"))
    shutil.rmtree(data_dir / str(gone.id))

    fresh = ProjectRepository(data_dir)
    await fresh.init()
    assert [p.id for p in await fresh.list_projects()] == [kept.id]


async def test_init_creates_empty_index(repo: ProjectRepository) -> None:
    assert read_index(repo) == {"schema_version": 1, "projects": []}


async def test_init_repairs_corrupt_index(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    repo = ProjectRepository(data_dir)
    await repo.init()
    project = await repo.create(new_project())
    repo.index_path.write_text("{roto", encoding="utf-8")

    fresh = ProjectRepository(data_dir)
    await fresh.init()
    assert [p.id for p in await fresh.list_projects()] == [project.id]


async def test_reindex_skips_corrupt_projects(repo: ProjectRepository) -> None:
    good = await repo.create(new_project("Bueno"))
    bad = await repo.create(new_project("Corrupto"))
    (repo.data_dir / str(bad.id) / "metadatos.json").write_text("{roto", encoding="utf-8")
    assert await repo.reindex() == 1
    assert [p.id for p in await repo.list_projects()] == [good.id]


# --- CLI -------------------------------------------------------------------------------


def test_cli_create_and_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = str(tmp_path / "data")
    assert cli_main(["--data-dir", data_dir, "crear", "Dormitorio", "--tipo", "dormitorio"]) == 0
    assert "Proyecto creado" in capsys.readouterr().out
    assert cli_main(["--data-dir", data_dir, "listar"]) == 0
    assert "Dormitorio" in capsys.readouterr().out
    assert cli_main(["--data-dir", data_dir, "ver", str(uuid4())]) == 1
