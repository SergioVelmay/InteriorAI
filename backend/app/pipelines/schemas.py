"""JSON Schema estricto (structured outputs) generado desde modelos Pydantic.

Modo estricto: todas las propiedades en `required`, `additionalProperties: false`, sin `$ref`
(se insertan las definiciones) y sin palabras clave no admitidas (`title`, `default`, límites
numéricos o de longitud). Pydantic sigue validando esos límites al recibir la respuesta.
"""

from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel

_DROPPED = frozenset(
    {
        "title", "default", "minLength", "maxLength", "pattern", "format", "minimum",
        "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minItems",
        "maxItems", "uniqueItems",
    }
)  # fmt: skip


def _transform(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, list):
        return [_transform(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        return _transform(copy.deepcopy(defs[name]), defs)
    result = {key: _transform(value, defs) for key, value in node.items() if key not in _DROPPED}
    if "properties" in node:
        # Las claves de `properties` son nombres de campo (p. ej. "title"), no palabras clave.
        result["properties"] = {
            name: _transform(sub, defs) for name, sub in node["properties"].items()
        }
        result["required"] = list(result["properties"])
        result["additionalProperties"] = False
    return result


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})
    return _transform(schema, defs)
