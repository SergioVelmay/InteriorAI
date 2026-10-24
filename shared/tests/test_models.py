from uuid import uuid4

import pytest
from pydantic import ValidationError

from shared.models import (
    AssetKind,
    ProjectCreate,
    ProjectIndex,
    ProjectMetadata,
    ProjectUpdate,
    utc_now,
)


def test_every_asset_kind_has_folder() -> None:
    assert {k.folder for k in AssetKind} == {
        "planos",
        "referencias",
        "capturas_sketchup",
        "renders_historico",
    }


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
    assert metadata.schema_version == 2
    assert ProjectIndex(projects=[metadata.summary()]).schema_version == 2
    assert '"schema_version":2' in metadata.model_dump_json()
