"""Tabla de precios (`config/pricing.yaml`) y cálculo del coste estimado de cada llamada."""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.foundry.types import Usage

logger = logging.getLogger("interiorai.telemetry")

PER_MILLION = 1_000_000


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TokenRates(_Model):
    input: float = Field(ge=0)
    cached_input: float = Field(ge=0)
    cache_write: float = Field(default=0, ge=0)
    output: float = Field(ge=0)


class TokenPricing(_Model):
    type: Literal["tokens"]
    rates: dict[Literal["global", "data_zone"], dict[Literal["short", "long"], TokenRates]]


class ImageTokenPricing(_Model):
    type: Literal["image_tokens"]
    input_text: float = Field(ge=0)
    cached_input_text: float = Field(ge=0)
    input_image: float = Field(ge=0)
    cached_input_image: float = Field(ge=0)
    output_image: float = Field(ge=0)


class MegapixelPricing(_Model):
    type: Literal["megapixels"]
    initial_mp: float = Field(ge=0)
    additional_mp: float = Field(ge=0)
    reference_mp: float = Field(ge=0)
    # pixels: según el tamaño de cada referencia (lo que factura FLUX, Paso 39) | per_image:
    # 1 MP por referencia, sea cual sea su tamaño
    reference_mode: Literal["pixels", "per_image"] = "pixels"


DeploymentPricing = Annotated[
    TokenPricing | ImageTokenPricing | MegapixelPricing, Field(discriminator="type")
]


class PricingTable(_Model):
    schema_version: Literal[1] = 1
    currency: str = "EUR"
    deployment_type: Literal["global", "data_zone"] = "global"
    long_context_threshold_tokens: int | None = Field(default=None, gt=0)
    megapixel_rounding: Literal["exact", "ceil"] = "exact"
    # Píxeles por megapíxel: 1.000.000 (decimal) o 1.048.576 (2^20, lo que factura Azure)
    megapixel_px: int = Field(default=PER_MILLION, gt=0)
    # Factor sobre los precios de lista (p. ej. el tipo de cambio observado en la factura)
    billing_factor: float = Field(default=1.0, gt=0)
    deployments: dict[str, DeploymentPricing]


class CostBreakdown(_Model):
    total: float
    parts: dict[str, float]
    tier: str


def load_pricing(path: Path) -> PricingTable | None:
    """Carga la tabla; si falta o no es válida, avisa y devuelve None (costes sin estimar)."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return PricingTable.model_validate(raw)
    except FileNotFoundError:
        logger.warning("Tabla de precios no encontrada en %s: costes sin estimar", path)
    except (yaml.YAMLError, ValidationError) as exc:
        logger.error("Tabla de precios inválida en %s: %s", path, exc)
    return None


def missing_prices(pricing: PricingTable, deployments: Iterable[str]) -> list[str]:
    return sorted({d for d in deployments if d not in pricing.deployments})


def megapixels(
    width: int, height: int, rounding: str = "exact", px_per_mp: int = PER_MILLION
) -> float:
    mp = width * height / px_per_mp
    return float(math.ceil(mp)) if rounding == "ceil" else mp


def _round(parts: dict[str, float], tier: str, factor: float = 1.0) -> CostBreakdown:
    scaled = {k: v * factor for k, v in parts.items()}
    rounded = {k: round(v, 8) for k, v in scaled.items()}
    return CostBreakdown(total=round(sum(scaled.values()), 8), parts=rounded, tier=tier)


def _tokens_cost(pricing: TokenPricing, table: PricingTable, usage: Usage) -> CostBreakdown:
    threshold = table.long_context_threshold_tokens
    context = "long" if threshold and usage.input_tokens > threshold else "short"
    rates = pricing.rates[table.deployment_type][context]
    cached = min(usage.cached_input_tokens, usage.input_tokens)
    writes = min(usage.cache_write_tokens, usage.input_tokens - cached)
    fresh = usage.input_tokens - cached - writes
    parts = {
        "input": fresh * rates.input / PER_MILLION,
        "cached_input": cached * rates.cached_input / PER_MILLION,
        "cache_write": writes * rates.cache_write / PER_MILLION,
        "output": usage.output_tokens * rates.output / PER_MILLION,
    }
    return _round(parts, f"{table.deployment_type}/{context}", table.billing_factor)


def _image_tokens_cost(
    pricing: ImageTokenPricing, table: PricingTable, usage: Usage
) -> CostBreakdown:
    text, image = usage.input_text_tokens, usage.input_image_tokens
    if text + image == 0:  # sin desglose: toda la entrada se considera texto
        text = usage.input_tokens
    parts = {
        "input_text": text * pricing.input_text / PER_MILLION,
        "input_image": image * pricing.input_image / PER_MILLION,
        "output": usage.output_tokens * pricing.output_image / PER_MILLION,
    }
    return _round(parts, "image_tokens", table.billing_factor)


def _megapixels_cost(
    pricing: MegapixelPricing,
    table: PricingTable,
    images_out: list[tuple[int, int]],
    references: list[tuple[int, int]],
) -> CostBreakdown:
    rounding, unit = table.megapixel_rounding, table.megapixel_px
    initial = additional = 0.0
    for width, height in images_out:
        mp = megapixels(width, height, rounding, unit)
        initial += min(mp, 1.0) * pricing.initial_mp
        additional += max(mp - 1.0, 0.0) * pricing.additional_mp
    if pricing.reference_mode == "per_image":
        reference_mp = float(len(references))
    else:
        reference_mp = sum(megapixels(w, h, rounding, unit) for w, h in references)
    parts = {
        "initial_mp": initial,
        "additional_mp": additional,
        "reference_mp": reference_mp * pricing.reference_mp,
    }
    tier = f"megapixels/{rounding}" + ("" if unit == PER_MILLION else f"/{unit}px")
    return _round(parts, tier, table.billing_factor)


def estimate_cost(
    table: PricingTable | None,
    deployment: str,
    usage: Usage,
    images_out: list[tuple[int, int]] | None = None,
    references: list[tuple[int, int]] | None = None,
) -> CostBreakdown | None:
    """Coste estimado de una llamada, o None si el despliegue no tiene precio."""
    if table is None or deployment not in table.deployments:
        return None
    pricing = table.deployments[deployment]
    if isinstance(pricing, TokenPricing):
        return _tokens_cost(pricing, table, usage)
    if isinstance(pricing, ImageTokenPricing):
        return _image_tokens_cost(pricing, table, usage)
    return _megapixels_cost(pricing, table, images_out or [], references or [])
