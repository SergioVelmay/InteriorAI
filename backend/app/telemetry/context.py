"""Contexto de telemetría por tarea asíncrona (`contextvars`).

- `request_id`: lo fija el middleware HTTP para cada petición.
- `project_id`: lo fija quien llama a la IA con `telemetry_scope(project_id)`; sin él, las
  llamadas solo se registran en el log, no en `costes_telemetria.jsonl`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

_request_id: ContextVar[str | None] = ContextVar("interiorai_request_id", default=None)
_project_id: ContextVar[UUID | None] = ContextVar("interiorai_project_id", default=None)


def current_request_id() -> str | None:
    return _request_id.get()


def current_project_id() -> UUID | None:
    return _project_id.get()


@contextmanager
def request_scope(request_id: str) -> Iterator[None]:
    token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)


@contextmanager
def telemetry_scope(project_id: UUID | str) -> Iterator[None]:
    token = _project_id.set(UUID(str(project_id)))
    try:
        yield
    finally:
        _project_id.reset(token)
