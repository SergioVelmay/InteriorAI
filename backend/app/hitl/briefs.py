"""Revisión humana de los briefs: editar, aprobar o rechazar (solo por acción del usuario)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.hitl import BRIEF_TRANSITIONS, TransitionError, ensure_transition
from app.storage import ProjectRepository
from shared.models import (
    BriefStatus,
    DesignBrief,
    DesignBriefContent,
    FurnitureItem,
    ProjectMetadata,
    utc_now,
)


class BriefNotFoundError(LookupError):
    pass


class ImagePromptsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    fast_draft: str | None = Field(default=None, min_length=1)
    structural_composer: str | None = Field(default=None, min_length=1)
    photorealistic_renderer: str | None = Field(default=None, min_length=1)


class BriefContentUpdate(BaseModel):
    """Edición parcial del contenido de un brief propuesto."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1)
    summary: str | None = None
    spatial_constraints: list[str] | None = None
    furniture: list[FurnitureItem] | None = None
    palette: list[str] | None = None
    materials: list[str] | None = None
    lighting: str | None = None
    camera: str | None = None
    image_prompts: ImagePromptsUpdate | None = None
    open_questions: list[str] | None = None


def find_brief(metadata: ProjectMetadata, brief_id: UUID) -> DesignBrief:
    for brief in metadata.briefs:
        if brief.id == brief_id:
            return brief
    raise BriefNotFoundError(str(brief_id))


def _replace(metadata: ProjectMetadata, *briefs: DesignBrief) -> ProjectMetadata:
    by_id = {b.id: b for b in briefs}
    return metadata.model_copy(update={"briefs": [by_id.get(b.id, b) for b in metadata.briefs]})


async def edit_brief(
    repo: ProjectRepository, project_id: UUID, brief_id: UUID, update: BriefContentUpdate
) -> DesignBrief:
    def change(metadata: ProjectMetadata) -> tuple[ProjectMetadata, DesignBrief]:
        brief = find_brief(metadata, brief_id)
        if brief.status is not BriefStatus.PROPOSED:
            raise TransitionError(
                f"Solo se puede editar un brief propuesto (este está '{brief.status}'); "
                "genera una nueva versión"
            )
        changes: dict[str, Any] = update.model_dump(exclude_unset=True, exclude={"image_prompts"})
        if update.image_prompts is not None:
            prompts = brief.content.image_prompts.model_dump()
            prompts |= update.image_prompts.model_dump(exclude_unset=True, exclude_none=True)
            changes["image_prompts"] = prompts
        content = DesignBriefContent.model_validate(brief.content.model_dump() | changes)
        edited = brief.model_copy(
            update={"content": content, "edited_by_user": True, "updated_at": utc_now()}
        )
        return _replace(metadata, edited), edited

    return await repo.mutate(project_id, change)


async def approve_brief(repo: ProjectRepository, project_id: UUID, brief_id: UUID) -> DesignBrief:
    """Aprueba el brief; el aprobado anterior (si lo hay) pasa a `reemplazado`."""

    def change(metadata: ProjectMetadata) -> tuple[ProjectMetadata, DesignBrief]:
        brief = find_brief(metadata, brief_id)
        ensure_transition(BRIEF_TRANSITIONS, brief.status, BriefStatus.APPROVED, "el brief")
        now = utc_now()
        superseded = [
            b.model_copy(update={"status": BriefStatus.SUPERSEDED, "updated_at": now})
            for b in metadata.briefs
            if b.status is BriefStatus.APPROVED
        ]
        approved = brief.model_copy(
            update={"status": BriefStatus.APPROVED, "decided_at": now, "updated_at": now}
        )
        return _replace(metadata, approved, *superseded), approved

    return await repo.mutate(project_id, change)


async def reject_brief(
    repo: ProjectRepository, project_id: UUID, brief_id: UUID, feedback: str
) -> DesignBrief:
    def change(metadata: ProjectMetadata) -> tuple[ProjectMetadata, DesignBrief]:
        brief = find_brief(metadata, brief_id)
        ensure_transition(BRIEF_TRANSITIONS, brief.status, BriefStatus.REJECTED, "el brief")
        now = utc_now()
        rejected = brief.model_copy(
            update={
                "status": BriefStatus.REJECTED,
                "feedback": feedback.strip(),
                "decided_at": now,
                "updated_at": now,
            }
        )
        return _replace(metadata, rejected), rejected

    return await repo.mutate(project_id, change)


__all__ = [
    "BriefContentUpdate",
    "BriefNotFoundError",
    "TransitionError",
    "approve_brief",
    "edit_brief",
    "find_brief",
    "reject_brief",
]
