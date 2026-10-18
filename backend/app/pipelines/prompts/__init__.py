"""Prompts de sistema versionados (archivos `.md` junto a este módulo).

Se editan sin tocar código; cada salida guarda la versión (hash del contenido) que la generó.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

_DIR = Path(__file__).parent


@dataclass(frozen=True)
class SystemPrompt:
    name: str
    text: str
    version: str


@cache
def load_prompt(name: str) -> SystemPrompt:
    text = (_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
    version = f"{name}@{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}"
    return SystemPrompt(name=name, text=text, version=version)
