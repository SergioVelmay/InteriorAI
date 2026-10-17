"""Lectura validada y escritura atómica (decisión D4).

Se escribe en un temporal del mismo directorio, se fuerza a disco y se renombra con
`os.replace`: un lector ve siempre el archivo anterior completo o el nuevo completo.

En Windows (y en volúmenes de Docker Desktop sobre disco de Windows), `os.replace` puede
fallar con `PermissionError` si otro proceso (antivirus, indexador) tiene abierto el destino
un instante: se reintenta con esperas crecientes.
"""

from __future__ import annotations

import os
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

M = TypeVar("M", bound=BaseModel)

REPLACE_ATTEMPTS = 10
REPLACE_BACKOFF_S = 0.01


class CorruptDataError(RuntimeError):
    """Un JSON de `data/` no es legible o no cumple su esquema."""


def replace_with_retry(source: str | Path, target: str | Path) -> None:
    for attempt in range(1, REPLACE_ATTEMPTS + 1):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS:
                raise
            time.sleep(REPLACE_BACKOFF_S * attempt)


def write_bytes_atomic(path: Path, data: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        replace_with_retry(tmp_name, path)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise


def write_json_atomic(path: Path, model: BaseModel) -> None:
    write_bytes_atomic(path, model.model_dump_json(indent=2).encode("utf-8") + b"\n")


def read_json(path: Path, model_type: type[M]) -> M:
    try:
        return model_type.model_validate_json(path.read_bytes())
    except ValidationError as exc:
        raise CorruptDataError(
            f"{path.name} no es válido ({exc.error_count()} errores de esquema)"
        ) from exc
