"""Cliente Azure con HTTP interceptado (`httpx.MockTransport`): ninguna petición sale a la red."""

import base64
import io
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.foundry import (
    FoundryAuthError,
    FoundryBadRequestError,
    FoundryContentFilterError,
    FoundryIncompleteError,
    FoundryRateLimitError,
    ImageEditRequest,
    ImageRequest,
    InputImage,
    TextRequest,
)
from app.foundry.azure import AzureFoundryClient
from shared import Settings
from shared.roles import Role

ENDPOINT = "https://example.com"
FAKE_KEY = "fake-key-for-tests-0000"
RENDERER_PATH = "/providers/proveedor/v1/renderer"

Handler = Callable[[httpx.Request], httpx.Response]


def png(size: tuple[int, int] = (32, 32)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "#8b5cf6").save(buffer, "PNG")
    return buffer.getvalue()


PNG_B64 = base64.b64encode(png()).decode()


def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **extra: str) -> Settings:
    values = {
        "AI_PROVIDER_MODE": "azure",
        "AZURE_FOUNDRY_ENDPOINT": ENDPOINT,
        "AZURE_FOUNDRY_API_KEY": FAKE_KEY,
        "AZURE_FOUNDRY_RENDERER_PATH": RENDERER_PATH,
        "AZURE_FOUNDRY_MAX_RETRIES": "0",
        "DATA_DIR": str(tmp_path),
        **{role.env_var: f"dep-{role.value.lower()}" for role in Role},
        **extra,
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return Settings.load(env_file=None)


@pytest.fixture
def make_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[..., tuple[AzureFoundryClient, list[httpx.Request]]]:
    def factory(handler: Handler, **extra: str) -> tuple[AzureFoundryClient, list[httpx.Request]]:
        seen: list[httpx.Request] = []

        def recording(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        http = httpx.AsyncClient(transport=httpx.MockTransport(recording))
        return AzureFoundryClient(settings(tmp_path, monkeypatch, **extra), http_client=http), seen

    return factory


def responses_body(text: str = "hola", status: str = "completed", reasoning: int = 0) -> dict:
    return {
        "id": "resp_123",
        "object": "response",
        "created_at": 0,
        "model": "dep",
        "status": status,
        "incomplete_details": {"reason": "max_output_tokens"} if status == "incomplete" else None,
        "output": [
            {
                "type": "message",
                "id": "msg_1",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": 120,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 300,
            "output_tokens_details": {"reasoning_tokens": reasoning},
            "total_tokens": 420,
        },
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
    }


def body_of(request: httpx.Request) -> dict:
    return json.loads(request.content)


# --- Texto (Responses API) -------------------------------------------------------------------


async def test_text_request_shape_and_usage(make_client) -> None:
    client, seen = make_client(lambda r: httpx.Response(200, json=responses_body("Prompt")))
    result = await client.complete_text(
        Role.PROMPT_ENGINEER,
        TextRequest(
            input="Notas",
            instructions="Sistema",
            images=[InputImage(data=png())],
            max_output_tokens=200,
        ),
    )
    request = seen[0]
    assert str(request.url) == f"{ENDPOINT}/openai/v1/responses"
    assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
    body = body_of(request)
    assert body["model"] == "dep-prompt_engineer"
    assert body["store"] is False
    assert body["instructions"] == "Sistema"
    assert body["max_output_tokens"] == 200
    assert "reasoning" not in body
    content = body["input"][0]["content"]
    assert content[0] == {"type": "input_text", "text": "Notas"}
    assert content[1]["image_url"].startswith("data:image/png;base64,")

    assert result.text == "Prompt"
    assert result.response_id == "resp_123"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (120, 300)
    assert result.deployment == "dep-prompt_engineer"


async def test_auditor_sends_reasoning_effort_and_reads_reasoning_tokens(make_client) -> None:
    client, seen = make_client(
        lambda r: httpx.Response(200, json=responses_body(reasoning=250)),
        GEOMETRIC_AUDITOR_REASONING_EFFORT="max",
    )
    result = await client.complete_text(Role.GEOMETRIC_AUDITOR, TextRequest(input="Audita"))
    assert body_of(seen[0])["reasoning"] == {"effort": "max"}
    assert result.usage.reasoning_tokens == 250


async def test_json_schema_is_sent_and_parsed(make_client) -> None:
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }
    client, seen = make_client(lambda r: httpx.Response(200, json=responses_body('{"ok": true}')))
    result = await client.complete_text(
        Role.CONTEXT_MANAGER, TextRequest(input="x", json_schema=schema, schema_name="indice")
    )
    fmt = body_of(seen[0])["text"]["format"]
    assert fmt == {"type": "json_schema", "name": "indice", "schema": schema, "strict": True}
    assert result.data == {"ok": True}


async def test_incomplete_response_keeps_usage_for_billing(make_client) -> None:
    client, _ = make_client(lambda r: httpx.Response(200, json=responses_body(status="incomplete")))
    with pytest.raises(FoundryIncompleteError, match="max_output_tokens") as exc:
        await client.complete_text(Role.GEOMETRIC_AUDITOR, TextRequest(input="x"))
    assert exc.value.usage is not None
    assert exc.value.usage.output_tokens == 300


@pytest.mark.parametrize(
    ("status", "payload", "error"),
    [
        (401, {"error": {"code": "401", "message": "Access denied"}}, FoundryAuthError),
        (403, {"error": {"code": "403", "message": "Forbidden"}}, FoundryAuthError),
        (429, {"error": {"code": "429", "message": "Rate limit"}}, FoundryRateLimitError),
        (
            400,
            {"error": {"code": "content_filter", "message": "Filtered by policy"}},
            FoundryContentFilterError,
        ),
        (
            400,
            {"error": {"code": "invalid_value", "message": "Unsupported effort 'max'"}},
            FoundryBadRequestError,
        ),
    ],
)
async def test_openai_errors_are_translated(make_client, status, payload, error) -> None:
    client, _ = make_client(lambda r: httpx.Response(status, json=payload))
    with pytest.raises(error) as exc:
        await client.complete_text(Role.PROMPT_ENGINEER, TextRequest(input="x"))
    assert exc.value.role is Role.PROMPT_ENGINEER
    assert FAKE_KEY not in str(exc.value)


# --- Imágenes (API de imágenes de OpenAI) ----------------------------------------------------


async def test_generate_image_request_and_decoding(make_client) -> None:
    payload = {
        "created": 0,
        "data": [{"b64_json": PNG_B64}],
        "usage": {
            "input_tokens": 12,
            "output_tokens": 272,
            "total_tokens": 284,
            "input_tokens_details": {"text_tokens": 12, "image_tokens": 0},
        },
    }
    client, seen = make_client(lambda r: httpx.Response(200, json=payload))
    result = await client.generate_image(
        Role.FAST_DRAFT, ImageRequest(prompt="Salón", size="1024x1024", quality="low")
    )
    assert str(seen[0].url) == f"{ENDPOINT}/openai/v1/images/generations"
    body = body_of(seen[0])
    assert (body["model"], body["size"], body["quality"]) == ("dep-fast_draft", "1024x1024", "low")
    assert result.images[0].data == png()
    assert (result.images[0].width, result.images[0].height) == (32, 32)
    assert (result.usage.input_tokens, result.usage.output_tokens) == (12, 272)


async def test_edit_image_sends_multipart_with_mask(make_client) -> None:
    client, seen = make_client(
        lambda r: httpx.Response(200, json={"created": 0, "data": [{"b64_json": PNG_B64}]})
    )
    await client.edit_image(
        Role.STRUCTURAL_COMPOSER,
        ImageEditRequest(
            prompt="Sofá", images=[InputImage(data=png())], mask=InputImage(data=png())
        ),
    )
    request = seen[0]
    assert str(request.url) == f"{ENDPOINT}/openai/v1/images/edits"
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b'name="mask"' in request.content
    assert b"dep-structural_composer" in request.content


# --- Renderizador (API del proveedor) ----------------------------------------------------------


async def test_renderer_generation_request(make_client) -> None:
    client, seen = make_client(
        lambda r: httpx.Response(200, json={"data": [{"b64_json": PNG_B64}]})
    )
    result = await client.generate_image(
        Role.PHOTOREALISTIC_RENDERER,
        ImageRequest(prompt="Render", size="1024x768", output_format="jpeg", seed=7, n=2),
    )
    assert len(seen) == 2  # una petición por imagen
    request = seen[0]
    assert request.url.path == RENDERER_PATH
    assert request.url.params["api-version"] == "preview"
    assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
    body = body_of(request)
    assert body == {
        "model": "dep-photorealistic_renderer",
        "prompt": "Render",
        "width": 1024,
        "height": 768,
        "output_format": "jpeg",
        "seed": 7,
    }
    assert body_of(seen[1])["seed"] == 8
    assert len(result.images) == 2
    assert result.usage.total_tokens == 0


async def test_renderer_edit_sends_reference_images(make_client) -> None:
    client, seen = make_client(
        lambda r: httpx.Response(200, json={"data": [{"b64_json": PNG_B64}]})
    )
    await client.edit_image(
        Role.PHOTOREALISTIC_RENDERER,
        ImageEditRequest(
            prompt="Luz cálida", images=[InputImage(data=png()), InputImage(data=png())]
        ),
    )
    body = body_of(seen[0])
    assert body["input_image"] == PNG_B64
    assert body["input_image_2"] == PNG_B64
    assert "mask" not in body


async def test_renderer_accepts_url_responses(make_client) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=png((48, 48)))
        return httpx.Response(200, json={"result": {"sample": "https://example.com/img.png"}})

    client, _ = make_client(handler)
    result = await client.generate_image(Role.PHOTOREALISTIC_RENDERER, ImageRequest(prompt="x"))
    assert result.images[0].width == 48


async def test_renderer_retries_on_429_with_retry_after(make_client) -> None:
    responses = iter(
        [
            httpx.Response(429, headers={"retry-after": "0"}, json={"error": {"message": "slow"}}),
            httpx.Response(200, json={"data": [{"b64_json": PNG_B64}]}),
        ]
    )
    client, seen = make_client(lambda r: next(responses), AZURE_FOUNDRY_MAX_RETRIES="2")
    result = await client.generate_image(Role.PHOTOREALISTIC_RENDERER, ImageRequest(prompt="x"))
    assert len(seen) == 2
    assert len(result.images) == 1


@pytest.mark.parametrize(
    ("status", "payload", "error"),
    [
        (401, {"error": {"message": "bad key"}}, FoundryAuthError),
        (429, {"error": {"message": "slow"}}, FoundryRateLimitError),
        (
            400,
            {"error": {"code": "content_filter", "message": "blocked"}},
            FoundryContentFilterError,
        ),
        (400, {"detail": "input_image is a not valid base64"}, FoundryBadRequestError),
    ],
)
async def test_renderer_errors_are_translated(make_client, status, payload, error) -> None:
    client, _ = make_client(lambda r: httpx.Response(status, json=payload))
    with pytest.raises(error):
        await client.generate_image(Role.PHOTOREALISTIC_RENDERER, ImageRequest(prompt="x"))


async def test_renderer_api_version_is_configurable(make_client) -> None:
    client, seen = make_client(
        lambda r: httpx.Response(200, json={"data": [{"b64_json": PNG_B64}]}),
        AZURE_FOUNDRY_RENDERER_API_VERSION="2026-01-01",
    )
    await client.generate_image(Role.PHOTOREALISTIC_RENDERER, ImageRequest(prompt="x"))
    assert seen[0].url.params["api-version"] == "2026-01-01"
