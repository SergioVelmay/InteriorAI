"""Paso 35: el esquema OpenAPI publicado en la documentación coincide con la API."""

from app.openapi import OUTPUT, render, schema


def test_published_openapi_schema_is_up_to_date() -> None:
    assert OUTPUT.read_text(encoding="utf-8") == render(), (
        "docs/referencia/openapi.json no está al día: ejecuta `uv run python -m app.openapi` "
        "desde backend/"
    )


def test_openapi_schema_documents_every_group() -> None:
    spec = schema()
    tags = [t["name"] for t in spec["tags"]]
    used = {tag for path in spec["paths"].values() for op in path.values() for tag in op["tags"]}
    assert used <= set(tags), used - set(tags)  # todo endpoint en un grupo descrito
    assert spec["info"]["license"]["identifier"] == "MIT"
    assert "/api/v1/projects/{project_id}/briefs" not in spec["paths"]  # sin la v1 (Paso 33)
