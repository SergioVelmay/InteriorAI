"""CLI de mantenimiento del almacenamiento.

python -m app.storage crear "Salón principal" --tipo salon_cocina_comedor
python -m app.storage listar
python -m app.storage ver <id>
python -m app.storage reindexar
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.storage import CorruptDataError, InvalidPathError, ProjectNotFoundError, ProjectRepository
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
    return parser


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
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except ProjectNotFoundError as exc:
        print(f"Proyecto no encontrado: {exc}", file=sys.stderr)
    except (InvalidPathError, CorruptDataError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
