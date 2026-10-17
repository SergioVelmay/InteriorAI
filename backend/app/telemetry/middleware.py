"""Middleware HTTP (decisión D1): `X-Request-ID` por petición y latencia extremo a extremo.

El identificador se propaga a cada registro de telemetría de las llamadas a IA que la
petición provoque, uniendo la acción del usuario con su coste.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.telemetry.context import request_scope

logger = logging.getLogger("interiorai.http")

HEADER = "x-request-id"
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _incoming_id(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == HEADER.encode():
            candidate = value.decode("latin-1")
            return candidate if _VALID_ID.fullmatch(candidate) else None
    return None


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_id(scope) or uuid.uuid4().hex
        start = time.perf_counter()
        status_code = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message).append("X-Request-ID", request_id)
            await send(message)

        with request_scope(request_id):
            try:
                await self.app(scope, receive, send_with_id)
            finally:
                logger.info(
                    "%s %s -> %d (%.3fs) [%s]",
                    scope["method"],
                    scope["path"],
                    status_code,
                    time.perf_counter() - start,
                    request_id,
                )
