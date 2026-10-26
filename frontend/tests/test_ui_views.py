from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from shared.models import (
    Asset,
    AssetKind,
    ProjectMetadata,
    RenderRecord,
    RenderStage,
    RenderStatus,
    utc_now,
)
from shared.roles import Role
from ui.api_client import Health
from ui.covers import asset_path, cover_asset, cover_image
from ui.views import calls_label, form_values, header_html, parse_form, project_summary_md

SHA = "0" * 64


def asset(kind: AssetKind, mime: str = "image/png", **extra) -> Asset:
    asset_id = extra.pop("id", uuid4())
    return Asset(
        id=asset_id, kind=kind, stored_name=f"{asset_id}.png", original_name="x.png",
        mime_type=mime, size_bytes=1, sha256=SHA, **extra,
    )  # fmt: skip


def render(asset_id, stage: RenderStage, status: RenderStatus, minutes: int = 0) -> RenderRecord:
    return RenderRecord(
        id=asset_id, stage=stage, status=status, role=Role.FAST_DRAFT_MAKER, deployment="d",
        brief_id=uuid4(), brief_version=1, prompt="p", input_asset_ids=[], batch_id=uuid4(),
        size="1536x1024", created_at=utc_now() + timedelta(minutes=minutes),
    )  # fmt: skip


def project(**extra) -> ProjectMetadata:
    now = utc_now()
    return ProjectMetadata(
        id=uuid4(), name="Salón <cocina>",
        created_at=now, updated_at=now, **extra,
    )  # fmt: skip


# --- Cabecera ------------------------------------------------------------------------------


def test_header_shows_mode_and_active_project() -> None:
    mock = header_html(Health(status="ok", version="1", mode="mock", data_dir_writable=True), None)
    assert "Simulación · sin coste" in mock
    assert "Sin proyecto activo" in mock
    azure = header_html(
        Health(status="ok", version="1", mode="azure", data_dir_writable=True), project()
    )
    assert "Azure · con coste" in azure and "iai-warn" in azure
    assert "Salón &lt;cocina&gt;" in azure  # escapado
    # Orden (B-050): proyecto → backend → modo.
    assert azure.index("Proyecto:") < azure.index("Backend conectado") < azure.index("Azure")
    assert "Backend no disponible" in header_html(None, None)


def test_header_shows_spending_alerts() -> None:
    health = Health(status="ok", version="1", mode="azure", data_dir_writable=True)
    current = project()
    alerts = {
        "total": {"cost_eur": 10.4, "threshold_eur": 10.0, "exceeded": True},
        "projects": [{"project_id": str(current.id), "cost_eur": 3.2, "threshold_eur": 3.0,
                      "exceeded": True}],
    }  # fmt: skip
    html = header_html(health, current, alerts)
    assert "Gasto del proyecto: 3.20 €" in html and "Gasto total: 10.40 €" in html
    calm = header_html(health, current, {**alerts, "total": {**alerts["total"], "exceeded": False},
                                         "projects": []})  # fmt: skip
    assert "Gasto" not in calm


# --- Resumen y formulario ---------------------------------------------------------------------


def test_summary_counts_and_costs() -> None:
    final = asset(AssetKind.RENDER)
    p = project(
        assets=[asset(AssetKind.REFERENCIA), asset(AssetKind.REFERENCIA), final],
        renders=[render(final.id, RenderStage.FINAL, RenderStatus.SELECTED)],
    )
    costs = {
        "totals": {"cost_eur": 0.27, "calls": 9},
        "by_role": [{"key": "FAST_DRAFT_MAKER", "cost_eur": 0.02, "calls": 4},
                    {"key": "REALISTIC_RENDERER", "cost_eur": 0.25, "calls": 5}],
        "records": [{}] * 9,
    }  # fmt: skip
    md = project_summary_md(p, costs)
    assert "Imágenes de referencia: **2**" in md
    assert "renders finales: **1**" in md
    assert "Render final elegido: **sí**" in md
    assert "Gasto real estimado en IA: **0.2700 €** en 9 llamadas" in md
    # Desglose por rol, del más caro al más barato (B-027).
    assert md.index("REALISTIC_RENDERER: 0.2500 €") < md.index("FAST_DRAFT_MAKER: 0.0200 €")
    assert calls_label(costs) == "Llamadas de IA (9)"
    assert calls_label(costs | {"records": [{}] * 3}) == "Llamadas de IA (las 3 últimas de 9)"
    assert calls_label(None) == "Llamadas de IA"


def test_form_roundtrip() -> None:
    update = parse_form(form_values(project(description="Tonos nórdicos")))
    assert update.changes() == {"name": "Salón <cocina>", "description": "Tonos nórdicos"}


def test_form_validation() -> None:
    with pytest.raises(ValueError, match="nombre"):
        parse_form(["  ", ""])


def test_form_empty_description() -> None:
    assert parse_form(["Salón", None]).description == ""


# --- Portadas -----------------------------------------------------------------------------------


def test_cover_shows_the_most_advanced_image() -> None:
    """B-044: final seleccionado → último final → composición seleccionada → última composición
    → boceto seleccionado → primer boceto → primera referencia → relleno."""
    first_ref, second_ref = asset(AssetKind.REFERENCIA), asset(AssetKind.REFERENCIA)
    ids = {name: asset(AssetKind.RENDER) for name in ("d1", "d2", "c1", "c2", "f1", "f2")}
    stage = {"d": RenderStage.DRAFT, "c": RenderStage.COMPOSITION, "f": RenderStage.FINAL}

    def cover(selected: set[str], present: tuple[str, ...]):
        renders = [
            render(ids[n].id, stage[n[0]],
                   RenderStatus.SELECTED if n in selected else RenderStatus.GENERATED,
                   minutes=int(n[1]))
            for n in present
        ]  # fmt: skip
        assets = [first_ref, second_ref, *(ids[n] for n in present)]
        return cover_asset(project(assets=assets, renders=renders))

    every = ("d1", "d2", "c1", "c2", "f1", "f2")
    assert cover({"f1"}, every) == ids["f1"]
    assert cover(set(), every) == ids["f2"]  # último render final
    assert cover({"c1"}, ("d1", "d2", "c1", "c2")) == ids["c1"]
    assert cover(set(), ("d1", "d2", "c1", "c2")) == ids["c2"]  # última composición
    assert cover({"d2"}, ("d1", "d2")) == ids["d2"]
    assert cover(set(), ("d1", "d2")) == ids["d1"]  # primer boceto
    assert cover(set(), ()) == first_ref
    pdf = asset(AssetKind.REFERENCIA, "application/pdf")
    assert cover_asset(project(assets=[pdf, second_ref])) == second_ref
    assert cover_asset(project()) is None  # sin imágenes: relleno


def test_cover_image_path_or_placeholder(tmp_path: Path) -> None:
    capture = asset(AssetKind.REFERENCIA)
    p = project(assets=[capture])
    placeholder = cover_image(p, tmp_path)  # el archivo aún no existe
    assert isinstance(placeholder, Image.Image)
    path = asset_path(tmp_path, p.id, capture)
    path.parent.mkdir(parents=True)
    Image.new("RGB", (10, 10)).save(path)
    assert cover_image(p, tmp_path) == str(path)
