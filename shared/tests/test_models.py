from uuid import uuid4

import pytest
from pydantic import ValidationError

from shared.models import (
    AssetKind,
    ProjectCreate,
    ProjectIndex,
    ProjectMetadata,
    ProjectUpdate,
    RenderRecord,
    TelemetryRecord,
    utc_now,
)
from shared.roles import Role


def test_every_asset_kind_has_folder() -> None:
    assert {k.folder for k in AssetKind} == {"referencias", "renders_historico"}


def test_project_create_strips_and_validates_name() -> None:
    assert ProjectCreate(name="  Salón  ").name == "Salón"
    with pytest.raises(ValidationError):
        ProjectCreate(name="   ")


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate(name="x", admin=True)
    with pytest.raises(ValidationError):  # campo de la v1 (B-026)
        ProjectCreate(name="x", space_type="salon")


def test_update_only_reports_fields_sent() -> None:
    assert ProjectUpdate(name="Nuevo").changes() == {"name": "Nuevo"}
    assert ProjectUpdate(description="").changes() == {"description": ""}


def test_metadata_and_index_carry_schema_version() -> None:
    now = utc_now()
    metadata = ProjectMetadata(id=uuid4(), name="x", created_at=now, updated_at=now)
    assert metadata.schema_version == 3  # sin la v1 (Paso 33)
    assert ProjectIndex(projects=[metadata.summary()]).schema_version == 2  # no cambia
    assert '"schema_version":3' in metadata.model_dump_json()


def test_telemetry_reads_the_previous_role_name() -> None:
    """B-052: los registros con CONTEXT_MANAGER (antes del Paso 18) son REFERENCE_ANALYST."""
    record = TelemetryRecord.model_validate(
        {"role": "CONTEXT_MANAGER", "deployment": "d", "operation": "complete_text",
         "status": "ok", "latency_s": 1.0}
    )  # fmt: skip
    assert record.role is Role.REFERENCE_ANALYST


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("PROMPT_ENGINEER", Role.PROMPT_ARCHITECT),
        ("GEOMETRIC_AUDITOR", Role.GEOMETRY_AUDITOR),
        ("FAST_DRAFT", Role.FAST_DRAFT_MAKER),
        ("STRUCTURAL_COMPOSER", Role.COMPOSITION_BUILDER),
        ("PHOTOREALISTIC_RENDERER", Role.REALISTIC_RENDERER),
    ],
)
def test_saved_data_reads_the_renamed_roles(old: str, new: Role) -> None:
    """Paso 26 (B-057): la telemetría y las imágenes de la 2.x se leen con el nombre actual."""
    record = TelemetryRecord.model_validate(
        {"role": old, "deployment": "d", "operation": "complete_text", "status": "ok",
         "latency_s": 1.0}
    )  # fmt: skip
    assert record.role is new
    render = RenderRecord.model_validate(
        {"id": str(uuid4()), "stage": "boceto", "role": old, "deployment": "d", "prompt": "p",
         "input_asset_ids": [], "batch_id": str(uuid4()), "size": "1024x1024"}
    )  # fmt: skip
    assert render.role is new
    assert render.model_dump(mode="json")["role"] == new.value  # se guarda con el nombre nuevo
