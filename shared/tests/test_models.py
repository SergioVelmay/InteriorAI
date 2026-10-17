from uuid import uuid4

import pytest
from pydantic import ValidationError

from shared.models import (
    AssetKind,
    ProjectCreate,
    ProjectIndex,
    ProjectMetadata,
    ProjectUpdate,
    SpaceType,
    utc_now,
)


def test_every_space_type_has_spanish_label() -> None:
    assert SpaceType.SALON_COCINA_COMEDOR.label == "Salón-cocina-comedor"
    assert all(t.label for t in SpaceType)


def test_every_asset_kind_has_folder() -> None:
    assert {k.folder for k in AssetKind} == {
        "planos",
        "referencias",
        "capturas_sketchup",
        "renders_historico",
    }


def test_project_create_strips_and_validates_name() -> None:
    assert ProjectCreate(name="  Salón  ", space_type="salon").name == "Salón"
    with pytest.raises(ValidationError):
        ProjectCreate(name="   ", space_type="salon")
    with pytest.raises(ValidationError):
        ProjectCreate(name="x", space_type="garaje")


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate(name="x", space_type="salon", admin=True)


def test_dimensions_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate(name="x", space_type="salon", dimensions={"width_m": 0, "length_m": 3})


def test_update_only_reports_fields_sent() -> None:
    assert ProjectUpdate(name="Nuevo").changes() == {"name": "Nuevo"}
    assert ProjectUpdate(dimensions=None).changes() == {"dimensions": None}


def test_metadata_and_index_carry_schema_version() -> None:
    now = utc_now()
    metadata = ProjectMetadata(
        id=uuid4(), name="x", space_type="estudio", created_at=now, updated_at=now
    )
    assert metadata.schema_version == 1
    assert ProjectIndex(projects=[metadata.summary()]).schema_version == 1
    assert '"schema_version":1' in metadata.model_dump_json()
