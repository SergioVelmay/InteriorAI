"""Human-in-the-Loop: transiciones de estado que solo ocurren por acción del usuario."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from shared.models import BriefStatus


class TransitionError(Exception):
    """Transición de estado no permitida (HTTP 409)."""


def ensure_transition(
    table: Mapping[StrEnum, frozenset[StrEnum]], current: StrEnum, target: StrEnum, what: str
) -> None:
    if target not in table.get(current, frozenset()):
        raise TransitionError(f"No se puede pasar {what} de '{current}' a '{target}'")


BRIEF_TRANSITIONS: dict[StrEnum, frozenset[StrEnum]] = {
    BriefStatus.PROPOSED: frozenset({BriefStatus.APPROVED, BriefStatus.REJECTED}),
    BriefStatus.APPROVED: frozenset({BriefStatus.SUPERSEDED}),
}
