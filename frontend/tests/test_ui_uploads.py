"""Formularios bloqueados mientras trabajan (B-107, B-108) y copias temporales de las subidas."""

from pathlib import Path
from uuid import uuid4

import gradio as gr
import httpx
from gradio.utils import get_upload_folder
from PIL import Image

from ui.api_client import BackendClient
from ui.tabs.projects import build_projects_tab
from ui.tabs.references import build_references_tab
from ui.uploads import discard_upload


def client() -> BackendClient:
    return BackendClient(
        "http://backend.test", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))
    )


def by_id(demo: gr.Blocks, elem_id: str):
    return next(b for b in demo.blocks.values() if getattr(b, "elem_id", None) == elem_id)


def chain(demo: gr.Blocks, outputs: list) -> list:
    """Funciones de eventos cuyas salidas son exactamente `outputs`, en orden de registro."""
    ids = [o._id for o in outputs]
    return [f for f in demo.fns.values() if [o._id for o in f.outputs] == ids]


def upload_copy(name: str = "vista.png") -> Path:
    """Una imagen en la carpeta de subidas de Gradio, como si se acabara de elegir."""
    folder = Path(get_upload_folder()) / f"test-{uuid4().hex}"
    folder.mkdir(parents=True)
    path = folder / name
    Image.new("RGB", (8, 8)).save(path)
    return path


def test_discard_upload_only_deletes_gradio_uploads(tmp_path: Path) -> None:
    path = upload_copy()
    assert discard_upload(str(path)) is True
    assert not path.exists() and not path.parent.exists()  # también su carpeta, vacía
    outside = tmp_path / "data.png"
    outside.write_bytes(b"x")
    assert discard_upload(str(outside)) is False and outside.exists()  # fuera: nunca
    assert discard_upload(None) is False and discard_upload(str(path)) is False


def test_project_form_is_locked_while_creating(tmp_path: Path) -> None:
    """B-107: lo que se escribe mientras se crea otro proyecto ya no se pierde."""
    with gr.Blocks() as demo:
        build_projects_tab(client(), tmp_path, gr.BrowserState(None), gr.HTML())
    create = by_id(demo, "iai-create")
    form = [by_id(demo, "iai-new-name"), by_id(demo, "iai-new-description"), create]
    lock, unlock = chain(demo, form)
    assert (create._id, "click") in lock.targets
    locked, unlocked = lock.fn(), unlock.fn()
    assert all(update["interactive"] is False for update in locked.values())
    assert locked[create]["value"] == "Creando…"
    assert all(update["interactive"] is True for update in unlocked.values())
    assert unlocked[create]["value"] == "Crear proyecto"


def test_reference_upload_preview_cancel_and_lock(tmp_path: Path) -> None:
    """B-108: vista previa de la imagen elegida, «Cancelar» y formulario bloqueado al subir."""
    with gr.Blocks() as demo:
        build_references_tab(client(), tmp_path, gr.BrowserState(None))
    file, notes = by_id(demo, "iai-reference-file"), by_id(demo, "iai-reference-upload-notes")
    upload, cancel = by_id(demo, "iai-reference-upload"), by_id(demo, "iai-reference-cancel")
    preview = by_id(demo, "iai-upload-preview")
    on_file = next(f for f in demo.fns.values() if f.name == "on_file")

    first, second = upload_copy("a.png"), upload_copy("b.png")
    shown = on_file.fn(str(first), None)
    assert shown[preview] == {"__type__": "update", "value": str(first), "visible": True}
    on_file.fn(str(second), str(first))  # otra imagen: la anterior se borra
    assert not first.exists() and second.exists()
    hidden = on_file.fn(None, str(second))  # cancelar o subirla: se borra y se oculta
    assert not second.exists() and hidden[preview]["visible"] is False

    [cancelled] = chain(demo, [file, notes])
    assert (cancel._id, "click") in cancelled.targets and cancelled.fn() == (None, "")
    lock, unlock = chain(demo, [file, notes, upload, cancel])
    assert lock.fn()[upload] == {
        "__type__": "update",
        "interactive": False,
        "value": "Subiendo y analizando…",
    }
    assert all(update["interactive"] is True for update in unlock.fn().values())
