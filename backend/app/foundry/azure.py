"""Cliente real de Azure AI Foundry (`AI_PROVIDER_MODE=azure`).

- `RESPONSES` e `IMAGES`: SDK `openai` contra `{endpoint}/openai/v1/` (API v1, sin api-version).
- `PROVIDER_IMAGES`: `httpx` contra `{renderer_endpoint}{renderer_path}?api-version=...`
  (API del proveedor: una imagen por petición; edición por imágenes de referencia).

Política de reintentos (Paso 10): solo se reintenta cuando Azure NO ha procesado la petición
(429 cuota, 503 no disponible). Un timeout NUNCA se reintenta: el trabajo pudo completarse y
facturarse en Azure aunque la respuesta no llegue. El auditor tiene su propio timeout.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

import httpx
import openai
from openai import AsyncOpenAI
from PIL import Image, UnidentifiedImageError

from app.foundry.base import FoundryClient, log_call, logger
from app.foundry.errors import (
    FoundryAuthError,
    FoundryBadRequestError,
    FoundryContentFilterError,
    FoundryError,
    FoundryIncompleteError,
    FoundryRateLimitError,
    FoundryTimeoutError,
)
from app.foundry.types import (
    GeneratedImage,
    ImageEditRequest,
    ImageRequest,
    ImageResult,
    TextRequest,
    TextResult,
    Usage,
)
from shared import Settings
from shared.roles import ApiKind, Role

T = TypeVar("T")
RETRYABLE_STATUS = frozenset({429, 503})  # Azure no ha procesado la petición

_CONTENT_FILTER_MARKERS = ("content_filter", "content_policy", "responsibleaipolicy", "moderation")
MAX_RETRY_DELAY_S = 30.0
RENDERER_MAX_IMAGES = 8  # input_image ... input_image_8


# --- Utilidades --------------------------------------------------------------------------


def _error_body(body: object) -> dict[str, Any]:
    if isinstance(body, dict):
        inner = body.get("error")
        return inner if isinstance(inner, dict) else body
    return {}


def _is_content_filter(body: dict[str, Any], message: str) -> bool:
    haystack = " ".join(
        str(v)
        for v in (body.get("code"), body.get("type"), body.get("innererror"), message)
        if v is not None
    ).lower()
    return any(marker in haystack for marker in _CONTENT_FILTER_MARKERS)


@contextmanager
def _openai_errors(role: Role) -> Iterator[None]:
    """Traduce las excepciones del SDK `openai` a errores `Foundry*`."""
    try:
        yield
    except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
        raise FoundryAuthError(
            f"Credenciales rechazadas por Azure ({exc.status_code})",
            role=role,
            status_code=exc.status_code,
        ) from exc
    except openai.RateLimitError as exc:
        raise FoundryRateLimitError(
            "Cuota de Azure agotada (429) tras los reintentos", role=role, status_code=429
        ) from exc
    except openai.APITimeoutError as exc:
        raise FoundryTimeoutError("Tiempo de espera agotado", role=role) from exc
    except openai.BadRequestError as exc:
        body = _error_body(exc.body)
        message = str(body.get("message") or exc.message)
        error = (
            FoundryContentFilterError
            if _is_content_filter(body, message)
            else (FoundryBadRequestError)
        )
        raise error(message, role=role, status_code=400) from exc
    except openai.APIStatusError as exc:
        body = _error_body(exc.body)
        raise FoundryError(
            f"Error de Azure ({exc.status_code}): {body.get('message') or exc.message}",
            role=role,
            status_code=exc.status_code,
        ) from exc
    except openai.APIConnectionError as exc:
        raise FoundryError("No se pudo conectar con Azure AI Foundry", role=role) from exc


def _to_generated(data: bytes, role: Role) -> GeneratedImage:
    try:
        with Image.open(io.BytesIO(data)) as image:
            fmt, width, height = image.format, image.width, image.height
    except (UnidentifiedImageError, OSError) as exc:
        raise FoundryError("El despliegue devolvió una imagen no válida", role=role) from exc
    return GeneratedImage(
        data=data, mime_type=f"image/{(fmt or 'png').lower()}", width=width, height=height
    )


def _retry_delay(response: Any, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return min(float(retry_after), MAX_RETRY_DELAY_S)
            except ValueError:
                pass
    return min(0.5 * 2**attempt, MAX_RETRY_DELAY_S)


# --- Cliente -------------------------------------------------------------------------------


class AzureFoundryClient(FoundryClient):
    """`http_client` (httpx) se usa para el renderizador. El SDK `openai` 3.x trae su propio
    cliente basado en `httpx2` (librería distinta): `openai_http_client` solo para tests."""

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
        openai_http_client: Any | None = None,
    ) -> None:
        foundry = settings.foundry
        if foundry.endpoint is None or foundry.api_key is None:
            raise FoundryAuthError("Falta AZURE_FOUNDRY_ENDPOINT o AZURE_FOUNDRY_API_KEY")
        self._settings = settings
        self._max_retries = foundry.max_retries
        self._timeout_s = foundry.timeout_s
        api_key = foundry.api_key.get_secret_value()

        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=foundry.timeout_s)
        openai_kwargs: dict[str, Any] = {}
        if openai_http_client is not None:
            openai_kwargs["http_client"] = openai_http_client
        self._openai = AsyncOpenAI(
            base_url=f"{foundry.endpoint}/openai/v1/",
            api_key=api_key,
            max_retries=0,  # reintentos propios: nunca ante timeouts (ver docstring)
            timeout=foundry.timeout_s,
            default_query={"api-version": foundry.api_version} if foundry.api_version else None,
            **openai_kwargs,
        )
        self._renderer_url = f"{foundry.renderer_base_url}{foundry.renderer_path or ''}"
        self._renderer_params = (
            {"api-version": foundry.renderer_api_version} if foundry.renderer_api_version else {}
        )
        self._renderer_headers = {"Authorization": f"Bearer {api_key}"}

    async def _openai_call(self, role: Role, call: Callable[[AsyncOpenAI], Awaitable[T]]) -> T:
        """Ejecuta una llamada del SDK reintentando solo 429/503 (nunca timeouts)."""
        client = (
            self._openai.with_options(timeout=self._settings.auditor.timeout_s)
            if role is Role.GEOMETRY_AUDITOR
            else self._openai
        )
        with _openai_errors(role):
            for attempt in range(self._max_retries + 1):
                try:
                    return await call(client)
                except openai.APIStatusError as exc:
                    if exc.status_code not in RETRYABLE_STATUS or attempt == self._max_retries:
                        raise
                    delay = _retry_delay(exc.response, attempt)
                    logger.warning(
                        "IA %s: %d, reintento %d/%d en %.1fs",
                        role.value, exc.status_code, attempt + 1, self._max_retries, delay,
                    )  # fmt: skip
                    await asyncio.sleep(delay)
        raise AssertionError("inalcanzable")  # pragma: no cover

    async def aclose(self) -> None:
        await self._openai.close()
        if self._owns_http:
            await self._http.aclose()

    # --- Texto (Responses API) ------------------------------------------------------------

    async def _complete_text(self, role: Role, request: TextRequest) -> TextResult:
        deployment = self._settings.deployment_for(role)
        content: list[dict[str, Any]] = [{"type": "input_text", "text": request.input}]
        content += [{"type": "input_image", "image_url": img.data_url()} for img in request.images]
        kwargs: dict[str, Any] = {
            "model": deployment,
            "input": [{"role": "user", "content": content}],
            "store": False,
        }
        if request.instructions:
            kwargs["instructions"] = request.instructions
        if request.max_output_tokens:
            kwargs["max_output_tokens"] = request.max_output_tokens
        if effort := self._settings.reasoning_effort(role):  # por rol en `.env` (B-053)
            kwargs["reasoning"] = {"effort": effort}
        if request.json_schema is not None:
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": request.schema_name,
                    "schema": request.json_schema,
                    "strict": True,
                }
            }

        start = time.perf_counter()
        response = await self._openai_call(role, lambda c: c.responses.create(**kwargs))
        latency = time.perf_counter() - start

        usage = Usage()
        if response.usage is not None:
            out_details = response.usage.output_tokens_details
            in_details = response.usage.input_tokens_details
            usage = Usage(
                input_tokens=response.usage.input_tokens,
                cached_input_tokens=(getattr(in_details, "cached_tokens", None) or 0),
                cache_write_tokens=(getattr(in_details, "cache_write_tokens", None) or 0),
                output_tokens=response.usage.output_tokens,
                reasoning_tokens=out_details.reasoning_tokens if out_details else 0,
            )
        log_call(role, deployment, latency, usage, f"status={response.status}")

        if response.status == "incomplete":
            reason = getattr(response.incomplete_details, "reason", None) or "desconocido"
            error = (
                FoundryContentFilterError
                if reason == "content_filter"
                else (FoundryIncompleteError)
            )
            raise error(f"Respuesta incompleta (motivo: {reason})", role=role, usage=usage)

        text = response.output_text
        data = None
        if request.json_schema is not None:
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise FoundryError(
                    "La respuesta no es JSON válido", role=role, usage=usage
                ) from exc
        return TextResult(
            role=role,
            deployment=deployment,
            text=text,
            data=data,
            usage=usage,
            latency_s=latency,
            response_id=response.id,
        )

    # --- Imágenes ---------------------------------------------------------------------------

    async def _generate_image(self, role: Role, request: ImageRequest) -> ImageResult:
        if role.api_kind is ApiKind.PROVIDER_IMAGES:
            return await self._provider_images(role, request, references=[])
        deployment = self._settings.deployment_for(role)
        start = time.perf_counter()
        response = await self._openai_call(
            role,
            lambda c: c.images.generate(
                model=deployment,
                prompt=request.prompt,
                size=request.size,  # type: ignore[arg-type]
                n=request.n,
                quality=request.quality,
                output_format=request.output_format,
            ),
        )
        return await self._openai_image_result(role, deployment, response, start)

    async def _edit_image(self, role: Role, request: ImageEditRequest) -> ImageResult:
        if role.api_kind is ApiKind.PROVIDER_IMAGES:
            return await self._provider_images(role, request, references=request.images)
        deployment = self._settings.deployment_for(role)
        files = [
            (f"imagen_{i}.{img.mime_type.split('/')[-1]}", img.data, img.mime_type)
            for i, img in enumerate(request.images)
        ]
        kwargs: dict[str, Any] = {
            "model": deployment,
            "image": files if len(files) > 1 else files[0],
            "prompt": request.prompt,
            "size": request.size,
            "n": request.n,
            "quality": request.quality,
            "output_format": request.output_format,
        }
        if request.mask is not None:
            kwargs["mask"] = ("mascara.png", request.mask.data, request.mask.mime_type)
            # Sin `input_fidelity` (B-041): el despliegue de retoques lo rechaza con un 400
            # (comprobado en el Paso 18) y conserva bien lo que queda fuera de la máscara.
        start = time.perf_counter()
        response = await self._openai_call(role, lambda c: c.images.edit(**kwargs))
        return await self._openai_image_result(role, deployment, response, start)

    async def _openai_image_result(
        self, role: Role, deployment: str, response: Any, start: float
    ) -> ImageResult:
        images = [
            await self._image_from_item(role, item.b64_json, item.url)
            for item in response.data or []
        ]
        if not images:
            raise FoundryError("El despliegue no devolvió imágenes", role=role)
        latency = time.perf_counter() - start
        usage = Usage()
        if getattr(response, "usage", None) is not None:
            details = response.usage.input_tokens_details
            usage = Usage(
                input_tokens=response.usage.input_tokens,
                input_text_tokens=(getattr(details, "text_tokens", None) or 0),
                input_image_tokens=(getattr(details, "image_tokens", None) or 0),
                output_tokens=response.usage.output_tokens,
            )
        log_call(role, deployment, latency, usage, f"{len(images)} imagen(es)")
        return ImageResult(
            role=role, deployment=deployment, images=images, usage=usage, latency_s=latency
        )

    async def _image_from_item(
        self, role: Role, b64_json: str | None, url: str | None
    ) -> GeneratedImage:
        if b64_json:
            return _to_generated(base64.b64decode(b64_json), role)
        if url:
            try:
                response = await self._http.get(url, timeout=self._timeout_s)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise FoundryError("No se pudo descargar la imagen generada", role=role) from exc
            return _to_generated(response.content, role)
        raise FoundryError("La respuesta no contiene ninguna imagen", role=role)

    # --- Renderizador (API del proveedor) -----------------------------------------------------

    async def _provider_images(
        self, role: Role, request: ImageRequest, references: list[Any]
    ) -> ImageResult:
        if len(references) > RENDERER_MAX_IMAGES:
            raise FoundryError(
                f"El renderizador admite hasta {RENDERER_MAX_IMAGES} imágenes de entrada", role=role
            )
        deployment = self._settings.deployment_for(role)
        payload: dict[str, Any] = {
            "model": deployment,
            "prompt": request.prompt,
            "width": request.width,
            "height": request.height,
            "output_format": request.output_format,
        }
        for i, image in enumerate(references):
            key = "input_image" if i == 0 else f"input_image_{i + 1}"
            payload[key] = base64.b64encode(image.data).decode()

        start = time.perf_counter()
        images = []
        for i in range(request.n):  # la API devuelve una imagen por petición
            if request.seed is not None:
                payload["seed"] = request.seed + i
            body = await self._provider_post(role, payload)
            images.append(await self._provider_image(role, body))
        latency = time.perf_counter() - start
        usage = Usage()  # el renderizador se factura por imagen, no por tokens
        log_call(role, deployment, latency, usage, f"{len(images)} imagen(es) {request.size}")
        return ImageResult(
            role=role, deployment=deployment, images=images, usage=usage, latency_s=latency
        )

    async def _provider_post(self, role: Role, payload: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(self._max_retries + 1):
            last = attempt == self._max_retries
            try:
                response = await self._http.post(
                    self._renderer_url,
                    params=self._renderer_params,
                    headers=self._renderer_headers,
                    json=payload,
                    timeout=self._timeout_s,
                )
            except httpx.TimeoutException as exc:  # nunca se reintenta (pudo facturarse)
                raise FoundryTimeoutError("Tiempo de espera agotado", role=role) from exc
            except httpx.HTTPError as exc:
                raise FoundryError("No se pudo conectar con el renderizador", role=role) from exc

            status = response.status_code
            if status in RETRYABLE_STATUS and not last:
                await asyncio.sleep(_retry_delay(response, attempt))
                continue
            if status == 429 or status >= 500:
                error = FoundryRateLimitError if status == 429 else FoundryError
                raise error(f"El renderizador respondió {status}", role=role, status_code=status)
            if status in {401, 403}:
                raise FoundryAuthError(
                    f"Credenciales rechazadas por el renderizador ({status})",
                    role=role,
                    status_code=status,
                )
            try:
                body = response.json()
            except ValueError:
                body = {}
            if status >= 400:
                detail = _error_body(body)
                message = str(detail.get("message") or detail.get("detail") or response.text[:300])
                error = (
                    FoundryContentFilterError
                    if _is_content_filter(detail, message)
                    else (FoundryBadRequestError if status == 400 else FoundryError)
                )
                raise error(message, role=role, status_code=status)
            return body
        raise FoundryError("Reintentos agotados", role=role)  # pragma: no cover

    async def _provider_image(self, role: Role, body: dict[str, Any]) -> GeneratedImage:
        data = body.get("data")
        if isinstance(data, list) and data:
            return await self._image_from_item(role, data[0].get("b64_json"), data[0].get("url"))
        result = body.get("result")
        if isinstance(result, dict) and result.get("sample"):
            return await self._image_from_item(role, None, result["sample"])
        raise FoundryError("La respuesta del renderizador no contiene ninguna imagen", role=role)
