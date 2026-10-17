"""Bloqueos por clave en dos niveles (decisión D4).

- `asyncio.Lock`: serializa las corrutinas del mismo proceso sin bloquear el event loop.
- `filelock`: serializa entre procesos (workers de uvicorn, CLI de mantenimiento).

Orden de adquisición obligatorio para evitar interbloqueos: proyecto → índice.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from filelock import FileLock

INDEX_KEY = "index"
LOCK_TIMEOUT_S = 30


class LockManager:
    def __init__(self, lock_dir: Path) -> None:
        self._lock_dir = lock_dir
        self._async_locks: dict[str, asyncio.Lock] = {}
        self._file_locks: dict[str, FileLock] = {}

    @asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        async_lock = self._async_locks.setdefault(key, asyncio.Lock())
        async with async_lock:
            file_lock = self._file_locks.get(key)
            if file_lock is None:
                # thread_local=False: se adquiere en un hilo del pool y se libera en otro.
                file_lock = FileLock(
                    self._lock_dir / f"{key}.lock", timeout=LOCK_TIMEOUT_S, thread_local=False
                )
                self._file_locks[key] = file_lock
            await anyio.to_thread.run_sync(file_lock.acquire)
            try:
                yield
            finally:
                file_lock.release()
