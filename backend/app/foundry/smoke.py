"""Verificación de los despliegues reales de Azure AI Foundry. CADA LLAMADA TIENE COSTE.

    python -m app.foundry.smoke                         # plan completo, confirmando cada llamada
    python -m app.foundry.smoke --role FAST_DRAFT       # solo un rol

Doble seguro: se niega a ejecutarse si `AI_PROVIDER_MODE` no es `azure` y pide confirmación
(`s`) antes de cada llamada. Las imágenes se guardan en `--out` (nunca en `data/`).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from app.foundry import (
    FoundryBadRequestError,
    FoundryClient,
    FoundryError,
    ImageEditRequest,
    ImageRequest,
    ImageResult,
    InputImage,
    TextRequest,
    TextResult,
    create_foundry_client,
)
from shared import Settings
from shared.roles import Role
from shared.settings import AuditorSettings

DEFAULT_OUT = Path("/tmp/interiorai-smoke")  # noqa: S108 — salida temporal del contenedor

ClientFactory = Callable[[Settings], FoundryClient]
Result = TextResult | ImageResult


@dataclass(frozen=True)
class Check:
    key: str
    role: Role
    description: str
    run: Callable[[FoundryClient], Awaitable[Result]]


def _room_sketch() -> tuple[bytes, bytes]:
    """Boceto base de un salón y máscara (zona transparente = donde va el sofá). Sin coste."""
    image = Image.new("RGB", (1024, 1024), (236, 232, 224))
    draw = ImageDraw.Draw(image)
    draw.polygon([(0, 700), (1024, 700), (1024, 1024), (0, 1024)], fill=(196, 170, 140))
    draw.rectangle((380, 180, 640, 520), fill=(200, 225, 240), outline=(90, 90, 90), width=6)
    mask = Image.new("RGBA", (1024, 1024), (0, 0, 0, 255))
    mask.paste((0, 0, 0, 0), (200, 560, 824, 900))
    buffers = io.BytesIO(), io.BytesIO()
    image.save(buffers[0], "PNG")
    mask.save(buffers[1], "PNG")
    return buffers[0].getvalue(), buffers[1].getvalue()


CONTEXT_SCHEMA = {
    "type": "object",
    "properties": {
        "estilo": {"type": "string"},
        "colores": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["estilo", "colores"],
    "additionalProperties": False,
}


def build_plan() -> list[Check]:
    base, mask = _room_sketch()
    return [
        Check(
            "1", Role.PROMPT_ENGINEER, "1 texto corto (≤ 200 tokens de salida)",
            lambda c: c.complete_text(Role.PROMPT_ENGINEER, TextRequest(
                instructions=(
                    "Eres un asistente de interiorismo. Responde en español, en una frase."
                ),
                input="Describe un salón nórdico de 20 m² con mucha luz natural.",
                max_output_tokens=200,
            )),
        ),
        Check(
            "2", Role.CONTEXT_MANAGER, "1 texto corto con salida JSON estructurada",
            lambda c: c.complete_text(Role.CONTEXT_MANAGER, TextRequest(
                instructions="Extrae estilo y colores del producto. Responde solo con el JSON.",
                input=(
                    "Sofá de tres plazas, tapizado gris claro, patas de roble, estilo escandinavo."
                ),
                json_schema=CONTEXT_SCHEMA,
                schema_name="producto",
                max_output_tokens=200,
            )),
        ),
        Check(
            "3", Role.GEOMETRIC_AUDITOR, "1 texto con reasoning_effort configurado (B-001)",
            lambda c: c.complete_text(Role.GEOMETRIC_AUDITOR, TextRequest(
                instructions="Eres un auditor de espacios interiores. Responde en dos frases.",
                input=(
                    "Un salón mide 4 x 6 m. Un sofá de 2,30 m de largo se coloca en la pared de "
                    "4 m, junto a una puerta de 0,90 m de ancho. ¿Cabe sin bloquear la puerta?"
                ),
                max_output_tokens=2000,
            )),
        ),
        Check(
            "4", Role.FAST_DRAFT, "1 imagen 1024x1024, calidad baja",
            lambda c: c.generate_image(Role.FAST_DRAFT, ImageRequest(
                prompt="Boceto rápido en acuarela de un salón nórdico luminoso, vista frontal",
                size="1024x1024",
                quality="low",
            )),
        ),
        Check(
            "5", Role.STRUCTURAL_COMPOSER, "1 edición 1024x1024 con máscara, calidad baja",
            lambda c: c.edit_image(Role.STRUCTURAL_COMPOSER, ImageEditRequest(
                prompt="Añade un sofá gris de tres plazas en la zona inferior marcada",
                size="1024x1024",
                quality="low",
                images=[InputImage(data=base)],
                mask=InputImage(data=mask),
            )),
        ),
        Check(
            "6", Role.PHOTOREALISTIC_RENDERER, "1 imagen 1024x1024 (B-003)",
            lambda c: c.generate_image(Role.PHOTOREALISTIC_RENDERER, ImageRequest(
                prompt=(
                    "Fotografía realista de un salón nórdico con sofá gris, suelo de roble y "
                    "luz natural de tarde, 35 mm"
                ),
                size="1024x1024",
                output_format="jpeg",
            )),
        ),
    ]  # fmt: skip


def _auditor_fallback(effort: str) -> Check:
    plan = {c.role: c for c in build_plan()}
    original = plan[Role.GEOMETRIC_AUDITOR]
    return Check("3b", original.role, f"repetición con reasoning_effort={effort}", original.run)


def _summarize(result: Result, out_dir: Path, key: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "deployment": result.deployment,
        "latency_s": round(result.latency_s, 2),
        "usage": result.usage.model_dump(),
    }
    if isinstance(result, TextResult):
        summary["text"] = result.text[:300]
        if result.data is not None:
            summary["data"] = result.data
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        files = []
        for i, image in enumerate(result.images):
            path = (
                out_dir / f"{key}_{result.role.value.lower()}_{i}.{image.mime_type.split('/')[-1]}"
            )
            path.write_bytes(image.data)
            files.append({"path": path.as_posix(), "size": f"{image.width}x{image.height}"})
        summary["images"] = files
    return summary


def _print_result(key: str, outcome: dict[str, Any]) -> None:
    if outcome["status"] == "ok":
        usage = outcome["usage"]
        print(
            f"  OK · {outcome['deployment']} · {outcome['latency_s']} s · tokens "
            f"entrada/salida/razonamiento {usage['input_tokens']}/{usage['output_tokens']}/"
            f"{usage['reasoning_tokens']}"
        )
        if "text" in outcome:
            print(f"  Texto: {outcome['text']}")
        for image in outcome.get("images", []):
            print(f"  Imagen: {image['path']} ({image['size']})")
    elif outcome["status"] == "error":
        print(f"  ERROR {outcome['error']}: {outcome['message']}")
        if outcome.get("usage"):
            print(f"  (facturado igualmente: {outcome['usage']})")
    else:
        print("  Omitida.")


async def _execute(
    check: Check, client: FoundryClient, out_dir: Path, confirm: Callable[[str], str]
) -> dict[str, Any]:
    print(f"\n[{check.key}] {check.role.value}: {check.description}")
    if confirm("  ¿Ejecutar esta llamada (tiene coste)? [s/N] ").strip().lower() != "s":
        return {"key": check.key, "role": check.role.value, "status": "skipped"}
    start = time.perf_counter()
    try:
        result = await check.run(client)
    except FoundryError as exc:
        return {
            "key": check.key,
            "role": check.role.value,
            "status": "error",
            "error": type(exc).__name__,
            "message": str(exc),
            "status_code": exc.status_code,
            "usage": exc.usage.model_dump() if exc.usage else None,
            "elapsed_s": round(time.perf_counter() - start, 2),
        }
    return {
        "key": check.key,
        "role": check.role.value,
        "status": "ok",
        **_summarize(result, out_dir, check.key),
    }


async def run(
    settings: Settings,
    roles: set[Role] | None,
    out_dir: Path,
    client_factory: ClientFactory,
    confirm: Callable[[str], str],
) -> list[dict[str, Any]]:
    outcomes = []
    client = client_factory(settings)
    try:
        for check in build_plan():
            if roles and check.role not in roles:
                continue
            outcome = await _execute(check, client, out_dir, confirm)
            _print_result(check.key, outcome)
            outcomes.append(outcome)

            effort = settings.auditor.reasoning_effort
            rejected_effort = (
                check.role is Role.GEOMETRIC_AUDITOR
                and outcome["status"] == "error"
                and outcome["error"] == FoundryBadRequestError.__name__
                and effort != "high"
            )
            if rejected_effort:
                print(f"\n  El despliegue rechazó reasoning_effort={effort}; se propone 'high'.")
                fallback_settings = settings.model_copy(
                    update={"auditor": AuditorSettings(reasoning_effort="high", _env_file=None)}
                )
                fallback_client = client_factory(fallback_settings)
                try:
                    fallback = await _execute(
                        _auditor_fallback("high"), fallback_client, out_dir, confirm
                    )
                finally:
                    await fallback_client.aclose()
                _print_result("3b", fallback)
                outcomes.append(fallback)
    finally:
        await client.aclose()
    return outcomes


def main(
    argv: list[str] | None = None,
    client_factory: ClientFactory = create_foundry_client,
    confirm: Callable[[str], str] = input,
) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m app.foundry.smoke", description=__doc__)
    parser.add_argument("--role", action="append", choices=[r.value for r in Role])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    settings = Settings.load()
    if settings.is_mock:
        print(
            "Bloqueado: AI_PROVIDER_MODE=mock. Para verificar contra Azure (con coste), el "
            "usuario debe poner AI_PROVIDER_MODE=azure en .env y recrear el backend."
        )
        return 2

    roles = {Role(r) for r in args.role} if args.role else None
    print(
        f"Verificación contra Azure AI Foundry ({settings.foundry.endpoint}). Cada llamada cuesta."
    )
    outcomes = asyncio.run(run(settings, roles, args.out, client_factory, confirm))

    args.out.mkdir(parents=True, exist_ok=True)
    report = args.out / "informe.json"
    report.write_text(json.dumps(outcomes, ensure_ascii=False, indent=2), encoding="utf-8")
    errors = sum(o["status"] == "error" for o in outcomes)
    oks = sum(o["status"] == "ok" for o in outcomes)
    print(f"\nResumen: {oks} OK, {errors} con error. Informe: {report.as_posix()}")
    print("Recuerda volver a AI_PROVIDER_MODE=mock en .env al terminar.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
