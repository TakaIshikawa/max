from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.openrouter_models import OpenRouterModelsAdapter
from max.types.signal import SignalSourceType


PAYLOAD = {
    "data": [
        {
            "id": "openai/gpt-4.1",
            "name": "GPT 4.1",
            "description": "Flagship model",
            "context_length": 1048576,
            "pricing": {"prompt": "0.000002", "completion": "0.000008"},
            "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
        },
        {
            "id": "anthropic/claude-small",
            "name": "Claude Small",
            "context_length": 200000,
            "pricing": {"prompt": "0.000001", "completion": "0.000003"},
            "architecture": {"modality": "text->text"},
        },
    ]
}


def test_openrouter_models_adapter_identity() -> None:
    adapter = OpenRouterModelsAdapter()

    assert adapter.name == "openrouter_models"
    assert adapter.source_type == SignalSourceType.REGISTRY.value


@pytest.mark.asyncio
async def test_openrouter_models_fetch_maps_model_metadata() -> None:
    adapter = OpenRouterModelsAdapter(config={"base_url": "https://example.test"})
    response = MagicMock()
    response.json.return_value = PAYLOAD

    with patch("max.sources.openrouter_models.fetch_with_retry", new_callable=AsyncMock, return_value=response) as fetch:
        signals = await adapter.fetch(limit=5)

    fetch.assert_awaited_once()
    signal = signals[0]
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "openrouter_models"
    assert signal.metadata["model_id"] == "openai/gpt-4.1"
    assert signal.metadata["provider"] == "openai"
    assert signal.metadata["context_length"] == 1048576
    assert signal.metadata["pricing"]["prompt"] == "0.000002"
    assert signal.metadata["modalities"] == ["text", "image"]


@pytest.mark.asyncio
async def test_openrouter_models_filters_deterministically() -> None:
    adapter = OpenRouterModelsAdapter(config={
        "providers": ["anthropic"],
        "min_context_length": 100000,
        "max_price_per_million_tokens": 4,
    })
    response = MagicMock()
    response.json.return_value = PAYLOAD

    with patch("max.sources.openrouter_models.fetch_with_retry", new_callable=AsyncMock, return_value=response):
        signals = await adapter.fetch(limit=5)

    assert [signal.metadata["model_id"] for signal in signals] == ["anthropic/claude-small"]


@pytest.mark.asyncio
async def test_openrouter_models_filters_by_model_id() -> None:
    adapter = OpenRouterModelsAdapter(config={"model_ids": ["openai/gpt-4.1"]})
    response = MagicMock()
    response.json.return_value = PAYLOAD

    with patch("max.sources.openrouter_models.fetch_with_retry", new_callable=AsyncMock, return_value=response):
        signals = await adapter.fetch(limit=5)

    assert [signal.metadata["provider"] for signal in signals] == ["openai"]
