"""Límite global del tamaño del cuerpo de las peticiones (middleware ASGI).

Corta antes de que Starlette reciba y guarde el cuerpo completo:
- si `Content-Length` supera el límite → 413 inmediato;
- si no hay `Content-Length` (chunked), cuenta los bytes recibidos y aborta al superarlo.
"""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    def _reject(self) -> JSONResponse:
        mb = self.max_body_bytes / (1024 * 1024)
        return JSONResponse(
            {"detail": f"La petición supera el tamaño máximo permitido ({mb:.0f} MB)"},
            status_code=413,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = dict(scope["headers"]).get(b"content-length")
        if (
            content_length
            and content_length.isdigit()
            and int(content_length) > self.max_body_bytes
        ):
            await self._reject()(scope, receive, send)
            return

        received = 0
        response_started = False
        rejected = False

        async def limited_receive() -> Message:
            # Al superar el límite se responde 413 aquí mismo y la app ve una desconexión:
            # FastAPI convierte cualquier excepción al leer el cuerpo en un 400 genérico.
            nonlocal received, rejected
            if rejected:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    rejected = True
                    if not response_started:
                        await self._reject()(scope, receive, send)
                    return {"type": "http.disconnect"}
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if rejected:
                return  # ya se respondió 413: se descarta la respuesta de la app
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except Exception:
            if not rejected:
                raise


def max_body_bytes(max_upload_bytes: int) -> int:
    """Base64 ocupa 4/3 del binario; se añade 1 MiB para el resto del JSON/multipart."""
    return max_upload_bytes * 4 // 3 + 1024 * 1024
