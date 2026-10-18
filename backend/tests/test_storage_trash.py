"""Papelera: listar, restaurar proyectos y vaciar con confirmación (B-007)."""

import asyncio
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.storage import ProjectRepository
from app.storage.__main__ import main as cli_main
from app.storage.trash import TrashError, scan, selection
from shared.models import AssetKind, ProjectCreate, SpaceType

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture
async def repo(tmp_path: Path) -> ProjectRepository:
    repository = ProjectRepository(tmp_path / "data")
    await repository.init()
    return repository


async def deleted_project(repo: ProjectRepository, name: str = "Dormitorio") -> str:
    project = await repo.create(ProjectCreate(name=name, space_type=SpaceType.DORMITORIO))
    await repo.add_asset(project.id, AssetKind.REFERENCIA, PNG, "cama.png", "image/png")
    return (await repo.delete(project.id)).name


async def test_list_and_restore_a_project(repo: ProjectRepository) -> None:
    entry = await deleted_project(repo)
    kept = await repo.create(ProjectCreate(name="Salón", space_type=SpaceType.SALON))
    asset = await repo.add_asset(kept.id, AssetKind.REFERENCIA, PNG, "sofa.png", "image/png")
    await repo.remove_asset(kept.id, asset.id)

    projects, files = await repo.list_trash()
    assert [(p.entry, p.name) for p in projects] == [(entry, "Dormitorio")]
    assert projects[0].size_bytes > len(PNG)
    assert [f.project_id for f in files] == [kept.id] and files[0].size_bytes == len(PNG)

    restored = await repo.restore_project(entry)
    assert restored.name == "Dormitorio" and len(restored.assets) == 1
    assert {p.name for p in await repo.list_projects()} == {"Dormitorio", "Salón"}
    assert (await repo.list_trash())[0] == []

    with pytest.raises(TrashError, match="No hay ningún proyecto"):
        await repo.restore_project(entry)
    with pytest.raises(TrashError):
        await repo.restore_project("../../etc")


async def test_restore_never_overwrites(repo: ProjectRepository, tmp_path: Path) -> None:
    entry = await deleted_project(repo)
    project_id = entry[:36]
    (repo.data_dir / project_id).mkdir()  # ocupado (p. ej. restaurado a mano)
    with pytest.raises(TrashError, match="no se sobrescribe"):
        await repo.restore_project(entry)
    assert (repo.trash_dir / entry).is_dir()


async def test_empty_by_age_and_unknown_entries_are_kept(repo: ProjectRepository) -> None:
    old = await deleted_project(repo, "Viejo")
    await asyncio.sleep(0.01)
    recent = await deleted_project(repo, "Reciente")
    (repo.trash_dir / "notas-mias.txt").write_text("no tocar", encoding="utf-8")

    now = datetime.strptime(recent[37:], "%Y%m%dT%H%M%S%fZ").replace(tzinfo=UTC)
    projects, files = selection(repo.trash_dir, timedelta(milliseconds=5), now=now)
    assert [p.name for p in projects] == ["Viejo"] and files == []
    freed = await repo.empty_trash(projects, files)
    assert freed > 0
    assert not (repo.trash_dir / old).exists() and (repo.trash_dir / recent).exists()

    projects, files = selection(repo.trash_dir, None)
    await repo.empty_trash(projects, files)
    assert scan(repo.trash_dir) == ([], [])
    assert (repo.trash_dir / "notas-mias.txt").exists()  # lo no reconocido nunca se borra


async def test_empty_removes_asset_files_and_their_folder(repo: ProjectRepository) -> None:
    project = await repo.create(ProjectCreate(name="Salón", space_type=SpaceType.SALON))
    asset = await repo.add_asset(project.id, AssetKind.REFERENCIA, PNG, "sofa.png", "image/png")
    await repo.remove_asset(project.id, asset.id)
    await repo.empty_trash(*selection(repo.trash_dir, None))
    assert not (repo.trash_dir / str(project.id)).exists()


def test_cli_trash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    repo = ProjectRepository(data_dir)
    asyncio.run(repo.init())
    entry = asyncio.run(deleted_project(repo))
    args = ["--data-dir", str(data_dir), "papelera"]

    assert cli_main([*args, "listar"]) == 0
    assert entry in capsys.readouterr().out

    # Sin terminal no se vacía sin --si; con terminal hay que escribir VACIAR.
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert cli_main([*args, "vaciar"]) == 1
    assert "confirma con --si" in capsys.readouterr().err
    tty = io.StringIO("no\n")
    tty.isatty = lambda: True  # type: ignore[method-assign]
    monkeypatch.setattr("sys.stdin", tty)
    assert cli_main([*args, "vaciar"]) == 1
    assert "Cancelado" in capsys.readouterr().out
    assert (data_dir / ".papelera" / entry).is_dir()

    assert cli_main([*args, "restaurar", entry]) == 0
    assert "Proyecto restaurado" in capsys.readouterr().out
    assert cli_main([*args, "restaurar", entry]) == 1

    entry = asyncio.run(repo.delete(entry[:36])).name
    assert cli_main([*args, "vaciar", "--si"]) == 0
    assert "Papelera vaciada" in capsys.readouterr().out
    assert not (data_dir / ".papelera" / entry).exists()
    assert cli_main([*args, "vaciar", "--si"]) == 0
    assert "No hay nada que vaciar" in capsys.readouterr().out
