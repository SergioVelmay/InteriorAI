"""CLI de mantenimiento del almacenamiento.

python -m app.storage crear "Salón principal" --tipo salon_cocina_comedor
python -m app.storage listar
python -m app.storage ver <id>
python -m app.storage reindexar
python -m app.storage papelera listar
python -m app.storage papelera restaurar <entrada>
python -m app.storage papelera vaciar [--dias N] [--si]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import timedelta
from pathlib import Path

from app.storage import CorruptDataError, InvalidPathError, ProjectNotFoundError, ProjectRepository
from app.storage.trash import TrashError, selection
from shared import get_settings
from shared.models import ProjectCreate, SpaceType


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.storage", description=__doc__.split("\n")[0]
    )
    parser.add_argument("--data-dir", type=Path, help="Directorio de datos (por defecto DATA_DIR)")
    sub = parser.add_subparsers(dest="command", required=True)

    crear = sub.add_parser("crear", help="Crea un proyecto")
    crear.add_argument("nombre")
    crear.add_argument("--tipo", required=True, choices=[t.value for t in SpaceType])
    crear.add_argument("--descripcion", default="")

    sub.add_parser("listar", help="Lista los proyectos del índice")

    ver = sub.add_parser("ver", help="Muestra metadatos.json de un proyecto")
    ver.add_argument("id")

    sub.add_parser("reindexar", help="Reconstruye proyectos.json a partir de las carpetas")

    papelera = sub.add_parser("papelera", help="Lista, restaura o vacía la papelera")
    trash = papelera.add_subparsers(dest="trash_command", required=True)
    trash.add_parser("listar", help="Proyectos y archivos borrados")
    restaurar = trash.add_parser("restaurar", help="Devuelve un proyecto borrado a su sitio")
    restaurar.add_argument("entrada", help="Nombre de la entrada (columna «Entrada» de listar)")
    vaciar = trash.add_parser("vaciar", help="Borra DEFINITIVAMENTE (pide confirmación)")
    vaciar.add_argument("--dias", type=int, help="Solo lo borrado hace más de N días")
    vaciar.add_argument("--si", action="store_true", help="No pedir confirmación")
    return parser


def _mb(size: int) -> str:
    return f"{size / (1024 * 1024):.1f} MB"


async def _trash(repo: ProjectRepository, args: argparse.Namespace) -> int:
    if args.trash_command == "listar":
        projects, files = await repo.list_trash()
        if not projects and not files:
            print("La papelera está vacía.")
        if projects:
            print("Proyectos borrados (se pueden restaurar):")
            for p in projects:
                deleted = f"{p.deleted_at:%Y-%m-%d %H:%M} UTC"
                print(f"  {p.entry}  {p.name or '(sin nombre)'}  borrado {deleted}  "
                      f"{_mb(p.size_bytes)}")  # fmt: skip
        if files:
            size = sum(f.size_bytes for f in files)
            print(f"Archivos borrados de proyectos: {len(files)} ({_mb(size)}; no se restauran)")
        return 0
    if args.trash_command == "restaurar":
        project = await repo.restore_project(args.entrada)
        print(f"Proyecto restaurado: {project.id}  {project.name}")
        return 0

    older = timedelta(days=args.dias) if args.dias is not None else None
    projects, files = selection(repo.trash_dir, older)
    if not projects and not files:
        print("No hay nada que vaciar.")
        return 0
    size = sum(p.size_bytes for p in projects) + sum(f.size_bytes for f in files)
    print(f"Se borrarán DEFINITIVAMENTE {len(projects)} proyecto(s) y {len(files)} archivo(s) "
          f"({_mb(size)}).")  # fmt: skip
    for p in projects:
        print(f"  - {p.entry}  {p.name or '(sin nombre)'}")
    if not args.si:
        if not sys.stdin.isatty():
            print("Sin terminal interactiva: confirma con --si.", file=sys.stderr)
            return 1
        answer = await asyncio.to_thread(input, "Escribe VACIAR para confirmar: ")
        if answer.strip() != "VACIAR":
            print("Cancelado: no se ha borrado nada.")
            return 1
    freed = await repo.empty_trash(projects, files)
    print(f"Papelera vaciada: {_mb(freed)} liberados.")
    return 0


async def _run(args: argparse.Namespace) -> int:
    data_dir = args.data_dir or get_settings().storage.data_dir
    repo = ProjectRepository(data_dir)
    await repo.init()

    if args.command == "crear":
        project = await repo.create(
            ProjectCreate(name=args.nombre, space_type=args.tipo, description=args.descripcion)
        )
        print(f"Proyecto creado: {project.id}")
        print(f"Carpeta: {(data_dir / str(project.id)).as_posix()}")
    elif args.command == "listar":
        projects = await repo.list_projects()
        if not projects:
            print("No hay proyectos.")
        for p in projects:
            print(f"{p.id}  {p.space_type.label:<22} {p.name}  ({p.updated_at:%Y-%m-%d %H:%M} UTC)")
    elif args.command == "ver":
        print((await repo.get(args.id)).model_dump_json(indent=2))
    elif args.command == "reindexar":
        print(f"Índice reconstruido: {await repo.reindex()} proyectos")
    elif args.command == "papelera":
        return await _trash(repo, args)
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except ProjectNotFoundError as exc:
        print(f"Proyecto no encontrado: {exc}", file=sys.stderr)
    except (InvalidPathError, CorruptDataError, TrashError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
