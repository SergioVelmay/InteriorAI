"""Telemetría de un proyecto en JSONL (`costes_telemetria.jsonl`, B-012).

Una línea JSON por llamada a la IA: registrar una llamada es añadir una línea al final, sin
reescribir el archivo (antes, `costes_telemetria.json` se reescribía entero en cada llamada).
Es la única excepción a la escritura atómica con temporal + `os.replace`: si un corte deja una
línea incompleta al final, al leer se ignora con un aviso y el resto se conserva.

El formato anterior se migra solo (al arrancar y al usar un proyecto, p. ej. restaurado de la
papelera): se escribe el `.jsonl` de forma atómica y el `.json` se renombra a `.json.migrado`,
sin borrar nada.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from pydantic import ValidationError

from app.storage.atomic import read_json, replace_with_retry, write_bytes_atomic
from shared.models import TelemetryLog, TelemetryRecord

logger = logging.getLogger("interiorai.storage")

TELEMETRY_FILE = "costes_telemetria.jsonl"
LEGACY_TELEMETRY_FILE = "costes_telemetria.json"
MIGRATED_SUFFIX = ".migrado"


def _line(record: TelemetryRecord) -> bytes:
    return record.model_dump_json().encode("utf-8") + b"\n"


def create(root: Path) -> None:
    write_bytes_atomic(root / TELEMETRY_FILE, b"")


def migrate(root: Path) -> bool:
    """Convierte `costes_telemetria.json` en `.jsonl` si hace falta. Devuelve si migró."""
    legacy = root / LEGACY_TELEMETRY_FILE
    if not legacy.is_file():
        return False
    target = root / TELEMETRY_FILE
    if not target.exists():  # si ya existe, un arranque anterior migró y no llegó a renombrar
        log = read_json(legacy, TelemetryLog)
        write_bytes_atomic(target, b"".join(_line(r) for r in log.records))
    replace_with_retry(legacy, legacy.with_name(LEGACY_TELEMETRY_FILE + MIGRATED_SUFFIX))
    logger.info("Telemetría de %s migrada a JSONL", root.name)
    return True


def read(root: Path) -> list[TelemetryRecord]:
    migrate(root)
    path = root / TELEMETRY_FILE
    if not path.is_file():
        return []
    records = []
    for number, line in enumerate(path.read_bytes().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(TelemetryRecord.model_validate_json(line))
        except ValidationError:
            logger.warning("%s: línea %d ilegible, se ignora (¿escritura cortada?)", path, number)
    return records


def append(root: Path, record: TelemetryRecord) -> None:
    migrate(root)
    path = root / TELEMETRY_FILE
    # Una línea cortada al final no debe pegarse a la nueva.
    prefix = b"" if _ends_cleanly(path) else b"\n"
    with path.open("ab") as file:
        file.write(prefix + _line(record))
        file.flush()
        os.fsync(file.fileno())


def _ends_cleanly(path: Path) -> bool:
    """El archivo no existe, está vacío o termina en salto de línea."""
    if not path.is_file() or path.stat().st_size == 0:
        return True
    with path.open("rb") as file:
        file.seek(-1, os.SEEK_END)
        return file.read(1) == b"\n"
