"""Simulación de llamadas con telemetría (solo `AI_PROVIDER_MODE=mock`, sin coste).

    python -m app.telemetry simular <id_proyecto> [--llamadas 6]

Hace una llamada simulada por rol (en ciclo) dentro del proyecto. Los tokens son simulados y
el coste se estima con los precios reales de `pricing.yaml`; los registros quedan marcados
como `simulated`.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import sys
from pathlib import Path
from uuid import UUID

from PIL import Image

from app.foundry import ImageEditRequest, ImageRequest, InputImage, TextRequest
from app.storage import InvalidPathError, ProjectNotFoundError, ProjectRepository
from app.telemetry import create_metered_client, load_pricing, request_scope, telemetry_scope
from app.telemetry.metered import MeteredFoundryClient
from shared import Settings
from shared.roles import Role

ROLES = list(Role)


def _png(size: tuple[int, int], mode: str = "RGB", color: object = "#d4d4d8") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, "PNG")  # type: ignore[arg-type]
    return buffer.getvalue()


async def _call(client: MeteredFoundryClient, role: Role) -> None:
    if role in {Role.PROMPT_ENGINEER, Role.CONTEXT_MANAGER, Role.GEOMETRIC_AUDITOR}:
        await client.complete_text(
            role, TextRequest(input="Salón nórdico de 20 m² con mucha luz natural.")
        )
    elif role is Role.STRUCTURAL_COMPOSER:
        mask = Image.new("RGBA", (1024, 1024), (0, 0, 0, 255))
        mask.paste((0, 0, 0, 0), (200, 560, 824, 900))
        buffer = io.BytesIO()
        mask.save(buffer, "PNG")
        await client.edit_image(
            role,
            ImageEditRequest(
                prompt="Sofá gris de tres plazas",
                quality="low",
                images=[InputImage(data=_png((1024, 1024)))],
                mask=InputImage(data=buffer.getvalue()),
            ),
        )
    else:
        await client.generate_image(role, ImageRequest(prompt="Salón nórdico", quality="low"))


async def simulate(settings: Settings, project_id: UUID, calls: int) -> int:
    repo = ProjectRepository(settings.storage.data_dir)
    await repo.init()
    await repo.get(project_id)  # 404 antes de simular
    client = create_metered_client(settings, repo, load_pricing(settings.storage.pricing_file))
    try:
        with request_scope(f"simulacion-{project_id.hex[:8]}"), telemetry_scope(project_id):
            for i in range(calls):
                role = ROLES[i % len(ROLES)]
                await _call(client, role)
                print(f"  {i + 1:>2}. {role.value}")
    finally:
        await client.aclose()
    log = await repo.read_telemetry(project_id)
    total = sum(r.cost_eur or 0 for r in log.records)
    print(
        f"Registros en el proyecto: {len(log.records)} · coste estimado acumulado: {total:.6f} EUR"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m app.telemetry", description=__doc__)
    parser.add_argument("--data-dir", type=Path, help="Directorio de datos (por defecto DATA_DIR)")
    sub = parser.add_subparsers(dest="command", required=True)
    simular = sub.add_parser("simular", help="Llamadas simuladas con telemetría")
    simular.add_argument("project_id")
    simular.add_argument("--llamadas", type=int, default=len(ROLES))
    args = parser.parse_args(argv)

    settings = Settings.load()
    if not settings.is_mock:
        print("Bloqueado: la simulación solo se ejecuta con AI_PROVIDER_MODE=mock (sin coste).")
        return 2
    if args.data_dir:
        storage = settings.storage.model_copy(update={"data_dir": args.data_dir})
        settings = settings.model_copy(update={"storage": storage})
    try:
        return asyncio.run(simulate(settings, UUID(args.project_id), max(args.llamadas, 1)))
    except (ValueError, InvalidPathError):
        print(f"Identificador no válido: {args.project_id}", file=sys.stderr)
    except ProjectNotFoundError:
        print(f"Proyecto no encontrado: {args.project_id}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
