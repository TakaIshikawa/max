"""OpenRouter models source adapter."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterModelsAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "openrouter_models"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def base_url(self) -> str:
        value = self._config.get("base_url")
        return value.strip().rstrip("/") if isinstance(value, str) and value.strip() else DEFAULT_BASE_URL

    @property
    def timeout(self) -> float:
        return float(self._config.get("timeout", 30))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            payload = await self._fetch_json(client)
        models = payload.get("data") if isinstance(payload, dict) else payload
        signals: list[Signal] = []
        seen: set[str] = set()
        for record in models if isinstance(models, list) else []:
            if len(signals) >= limit:
                break
            if not isinstance(record, dict) or not self._passes_filters(record):
                continue
            model_id = _text(record.get("id"))
            if not model_id or model_id in seen:
                continue
            signal = _record_to_signal(record, self.name)
            if signal is None:
                continue
            seen.add(model_id)
            signals.append(signal)
        return signals

    async def _fetch_json(self, client: httpx.AsyncClient) -> Any:
        try:
            response = await fetch_with_retry(f"{self.base_url}/models", client, adapter_name=self.name)
            return response.json()
        except (AdapterFetchError, ValueError) as exc:
            logger.warning("%s: failed to fetch OpenRouter models: %s", self.name, exc)
            return None

    def _passes_filters(self, record: dict[str, Any]) -> bool:
        model_id = _text(record.get("id"))
        provider = _provider(record)
        if self._terms("model_ids") and model_id not in self._terms("model_ids"):
            return False
        if self._terms("providers") and provider not in self._terms("providers"):
            return False
        min_context = _number(self._config.get("min_context_length"))
        context = _context_length(record)
        if min_context is not None and (context is None or context < min_context):
            return False
        max_price = _number(self._config.get("max_price_per_million_tokens"))
        price = _max_price_per_million(record)
        if max_price is not None and (price is None or price > max_price):
            return False
        return True

    def _terms(self, key: str) -> list[str]:
        return self._configured_terms(key, [])


def _record_to_signal(record: dict[str, Any], adapter_name: str) -> Signal | None:
    model_id = _text(record.get("id"))
    if not model_id:
        return None
    name = _text(record.get("name")) or model_id
    provider = _provider(record)
    context = _context_length(record)
    pricing = record.get("pricing") if isinstance(record.get("pricing"), dict) else {}
    modalities = _modalities(record)
    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=name,
        content=_text(record.get("description")) or f"OpenRouter model {model_id}",
        url=f"https://openrouter.ai/{model_id}",
        tags=[item for item in (provider, *modalities) if item],
        credibility=0.65,
        metadata={
            "model_id": model_id,
            "provider": provider,
            "context_length": context,
            "pricing": pricing,
            "modalities": modalities,
        },
    )


def _provider(record: dict[str, Any]) -> str:
    explicit = _text(record.get("provider"))
    if explicit:
        return explicit
    model_id = _text(record.get("id"))
    return model_id.split("/", 1)[0] if "/" in model_id else ""


def _context_length(record: dict[str, Any]) -> int | None:
    value = record.get("context_length") or record.get("contextLength")
    parsed = _number(value)
    return int(parsed) if parsed is not None else None


def _max_price_per_million(record: dict[str, Any]) -> float | None:
    pricing = record.get("pricing")
    if not isinstance(pricing, dict):
        return None
    values = [_number(pricing.get(key)) for key in ("prompt", "completion", "input", "output")]
    values = [value * 1_000_000 for value in values if value is not None]
    return max(values) if values else None


def _modalities(record: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    architecture = record.get("architecture")
    if isinstance(architecture, dict):
        values.extend(architecture.get("input_modalities") or [])
        values.extend(architecture.get("output_modalities") or [])
        modality = architecture.get("modality")
        if isinstance(modality, str):
            values.extend(part.strip() for part in modality.split("->"))
    values.extend(record.get("modalities") or [])
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
