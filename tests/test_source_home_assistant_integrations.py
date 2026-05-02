"""Tests for the Home Assistant integrations source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.base import AdapterFetchError
from max.sources.home_assistant_integrations import (
    HOME_ASSISTANT_INTEGRATIONS_URL,
    HomeAssistantIntegrationsAdapter,
)
from max.types.signal import SignalSourceType


MOCK_INTEGRATIONS = [
    {
        "domain": "hue",
        "name": "Philips Hue",
        "description": "Control Philips Hue lights from Home Assistant.",
        "categories": ["light", "hub"],
        "quality_scale": "platinum",
        "iot_class": "local_push",
        "integration_type": "hub",
        "documentation": "https://www.home-assistant.io/integrations/hue/",
        "updated_at": "2026-04-20T12:30:00Z",
    },
    {
        "domain": "tesla_wall_connector",
        "name": "Tesla Wall Connector",
        "description": "Monitor Tesla Wall Connector charging hardware.",
        "categories": ["energy"],
        "quality_scale": "silver",
        "iot_class": "local_polling",
        "integration_type": "device",
        "updated_at": "2026-04-18T10:00:00Z",
    },
]


def test_home_assistant_integrations_adapter_properties() -> None:
    adapter = HomeAssistantIntegrationsAdapter()

    assert adapter.name == "home_assistant_integrations"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.integrations_url == HOME_ASSISTANT_INTEGRATIONS_URL
    assert adapter.integrations == []
    assert adapter.categories == []
    assert adapter.max_age_days is None


def test_home_assistant_integrations_adapter_custom_config() -> None:
    adapter = HomeAssistantIntegrationsAdapter(
        config={
            "integrations_url": "https://example.test/integrations.json",
            "integrations": ["hue", "tesla_wall_connector", "hue"],
            "categories": ["energy"],
            "watchlist_terms": ["local_polling"],
            "max_age_days": 30,
        }
    )

    assert adapter.integrations_url == "https://example.test/integrations.json"
    assert adapter.integrations == ["hue", "tesla_wall_connector"]
    assert adapter.categories == ["energy", "local_polling"]
    assert adapter.max_age_days == 30


@pytest.mark.asyncio
async def test_home_assistant_integrations_fetches_signals_from_mocked_catalog() -> None:
    adapter = HomeAssistantIntegrationsAdapter()

    with patch("max.sources.home_assistant_integrations.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"integrations": MOCK_INTEGRATIONS})

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_count == 1
    assert mock_fetch.call_args.args[0] == HOME_ASSISTANT_INTEGRATIONS_URL

    first = signals[0]
    assert first.id == "home_assistant_integrations:hue"
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "home_assistant_integrations"
    assert first.title == "Philips Hue Home Assistant integration"
    assert first.content == "Control Philips Hue lights from Home Assistant."
    assert first.url == "https://www.home-assistant.io/integrations/hue/"
    assert first.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert first.tags == [
        "home-assistant",
        "hue",
        "light",
        "hub",
        "quality:platinum",
        "iot:local_push",
        "type:hub",
    ]
    assert first.credibility > 0.8
    assert first.metadata["signal_role"] == "market"
    assert first.metadata["domain"] == "hue"
    assert first.metadata["name"] == "Philips Hue"
    assert first.metadata["categories"] == ["light", "hub"]
    assert first.metadata["quality_scale"] == "platinum"
    assert first.metadata["iot_class"] == "local_push"
    assert first.metadata["integration_type"] == "hub"
    assert first.metadata["integration_url"] == "https://www.home-assistant.io/integrations/hue/"
    assert first.metadata["source_url"] == HOME_ASSISTANT_INTEGRATIONS_URL


@pytest.mark.asyncio
async def test_home_assistant_integrations_respects_limit_and_deduplicates_domains() -> None:
    adapter = HomeAssistantIntegrationsAdapter()
    payload = [
        MOCK_INTEGRATIONS[0],
        {**MOCK_INTEGRATIONS[0], "name": "Duplicate Hue"},
        MOCK_INTEGRATIONS[1],
    ]

    with patch("max.sources.home_assistant_integrations.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: payload)

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["domain"] == "hue"

    with patch("max.sources.home_assistant_integrations.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: payload)

        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["domain"] for signal in signals] == ["hue", "tesla_wall_connector"]


@pytest.mark.asyncio
async def test_home_assistant_integrations_filters_integrations_and_categories() -> None:
    adapter = HomeAssistantIntegrationsAdapter(
        config={"integrations": ["tesla"], "categories": ["energy"]}
    )

    with patch("max.sources.home_assistant_integrations.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_INTEGRATIONS)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["domain"] == "tesla_wall_connector"


@pytest.mark.asyncio
async def test_home_assistant_integrations_handles_missing_optional_fields() -> None:
    adapter = HomeAssistantIntegrationsAdapter()
    payload = {"minimal": {"name": "Minimal Integration"}}

    with patch("max.sources.home_assistant_integrations.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: payload)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "home_assistant_integrations:minimal"
    assert signal.title == "Minimal Integration Home Assistant integration"
    assert signal.content == "Minimal Integration (minimal) is a Home Assistant integration."
    assert signal.url == "https://www.home-assistant.io/integrations/minimal/"
    assert signal.published_at is None
    assert signal.tags == ["home-assistant", "minimal"]
    assert signal.metadata["quality_scale"] is None
    assert signal.metadata["iot_class"] is None


@pytest.mark.asyncio
async def test_home_assistant_integrations_handles_http_and_malformed_payloads() -> None:
    adapter = HomeAssistantIntegrationsAdapter()

    with patch("max.sources.home_assistant_integrations.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = AdapterFetchError(
            "home_assistant_integrations",
            500,
            HOME_ASSISTANT_INTEGRATIONS_URL,
        )

        signals = await adapter.fetch(limit=10)

    assert signals == []

    with patch("max.sources.home_assistant_integrations.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"not": "a catalog"})

        signals = await adapter.fetch(limit=10)

    assert signals == []
