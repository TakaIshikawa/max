"""Tests for the APIs.guru source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.apis_guru import DEFAULT_BASE_URL, ApisGuruAdapter
from max.types.signal import SignalSourceType


MOCK_DIRECTORY = {
    "stripe.com": {
        "added": "2024-01-01T00:00:00Z",
        "preferred": "2023-10-16",
        "versions": {
            "2023-10-16": {
                "added": "2024-01-01T00:00:00Z",
                "updated": "2024-02-03T04:05:06Z",
                "swaggerUrl": "https://api.apis.guru/v2/specs/stripe.com/2023-10-16/openapi.json",
                "openapiVer": "3.0.0",
                "info": {
                    "title": "Stripe API",
                    "description": "Payments and billing platform APIs.",
                    "x-providerName": "stripe.com",
                    "categories": ["payments", "billing"],
                    "contact": {"url": "https://stripe.com/docs/api"},
                },
            },
            "2022-11-15": {
                "added": "2023-01-01T00:00:00Z",
                "updated": "2023-02-01T00:00:00Z",
                "swaggerUrl": "https://api.apis.guru/v2/specs/stripe.com/2022-11-15/openapi.json",
                "openapiVer": "3.0.0",
                "info": {
                    "title": "Stripe API",
                    "description": "Older payments API.",
                    "x-providerName": "stripe.com",
                    "categories": ["payments"],
                    "contact": {"url": "https://stripe.com/docs/api"},
                },
            },
        },
    },
    "twilio.com:messaging": {
        "preferred": "1.0.0",
        "versions": {
            "1.0.0": {
                "updated": "2024-03-01",
                "swaggerUrl": "https://api.apis.guru/v2/specs/twilio.com/messaging/1.0.0/openapi.json",
                "openapiVer": "3.1.0",
                "info": {
                    "title": "Twilio Messaging",
                    "description": "SMS and messaging workflows.",
                    "x-providerName": "twilio.com",
                    "x-serviceName": "messaging",
                    "categories": ["communications"],
                    "contact": {"url": "https://www.twilio.com/docs/messaging"},
                },
            }
        },
    },
}


def test_apis_guru_adapter_properties() -> None:
    adapter = ApisGuruAdapter()

    assert adapter.name == "apis_guru"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.base_url == DEFAULT_BASE_URL
    assert adapter.queries == []
    assert adapter.providers == []
    assert adapter.categories == []
    assert adapter.preferred_versions_only is True


def test_apis_guru_adapter_custom_config() -> None:
    adapter = ApisGuruAdapter(
        config={
            "base_url": "https://apis.example.test/v2/",
            "queries": ["billing"],
            "providers": ["stripe.com"],
            "categories": ["payments"],
            "watchlist_terms": ["developer"],
            "preferred_versions_only": "false",
        }
    )

    assert adapter.base_url == "https://apis.example.test/v2"
    assert adapter.queries == ["billing", "developer"]
    assert adapter.providers == ["stripe.com", "developer"]
    assert adapter.categories == ["payments", "developer"]
    assert adapter.preferred_versions_only is False


@pytest.mark.asyncio
async def test_apis_guru_fetch_emits_preferred_registry_signals() -> None:
    adapter = ApisGuruAdapter()

    with patch("max.sources.apis_guru.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_DIRECTORY)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == "https://api.apis.guru/v2/list.json"

    signal = signals[0]
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "apis_guru"
    assert signal.title == "Stripe API (2023-10-16)"
    assert signal.content == "Payments and billing platform APIs."
    assert signal.url == "https://stripe.com/docs/api"
    assert signal.published_at == datetime(2024, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
    assert signal.tags == ["stripe.com", "payments", "billing"]
    assert signal.metadata["provider"] == "stripe.com"
    assert signal.metadata["api_name"] == "stripe.com"
    assert signal.metadata["version"] == "2023-10-16"
    assert signal.metadata["preferred"] is True
    assert signal.metadata["swagger_url"].endswith("/stripe.com/2023-10-16/openapi.json")
    assert signal.metadata["openapi_ver"] == "3.0.0"
    assert signal.metadata["added"] == "2024-01-01T00:00:00Z"
    assert signal.metadata["updated"] == "2024-02-03T04:05:06Z"


@pytest.mark.asyncio
async def test_apis_guru_preferred_versions_only_controls_non_preferred_versions() -> None:
    adapter = ApisGuruAdapter(config={"preferred_versions_only": False})

    with patch("max.sources.apis_guru.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_DIRECTORY)

        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["version"] for signal in signals] == [
        "2023-10-16",
        "2022-11-15",
        "1.0.0",
    ]
    assert signals[1].metadata["preferred"] is False
    assert signals[1].credibility < signals[0].credibility


@pytest.mark.asyncio
async def test_apis_guru_filters_by_provider_query_and_category() -> None:
    adapter = ApisGuruAdapter(
        config={
            "providers": ["stripe.com"],
            "queries": ["billing"],
            "categories": ["payments"],
        }
    )

    with patch("max.sources.apis_guru.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_DIRECTORY)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["provider"] == "stripe.com"
    assert signals[0].metadata["categories"] == ["payments", "billing"]


@pytest.mark.asyncio
async def test_apis_guru_handles_missing_descriptions() -> None:
    adapter = ApisGuruAdapter()
    directory = {
        "example.com:maps": {
            "preferred": "v1",
            "versions": {
                "v1": {
                    "swaggerUrl": "https://api.apis.guru/v2/specs/example.com/maps/v1/openapi.json",
                    "info": {
                        "title": "Example Maps",
                        "x-providerName": "example.com",
                        "x-serviceName": "maps",
                    },
                }
            },
        }
    }

    with patch("max.sources.apis_guru.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: directory)

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert signals[0].title == "Example Maps (v1)"
    assert signals[0].content == "Example Maps (v1)"
    assert signals[0].url.endswith("/example.com/maps/v1/openapi.json")


@pytest.mark.asyncio
async def test_apis_guru_skips_malformed_payload_entries() -> None:
    adapter = ApisGuruAdapter()
    directory = {
        "broken": {"preferred": "v1"},
        "also-broken": {"versions": ["not", "a", "dict"]},
        "bad-version": {"versions": {"v1": "not a dict"}},
        "valid.example.com": {
            "versions": {
                "v1": {
                    "swaggerUrl": "https://api.apis.guru/v2/specs/valid.example.com/v1/openapi.json",
                    "info": {"title": "Valid API"},
                }
            }
        },
    }

    with patch("max.sources.apis_guru.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: directory)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["provider"] == "valid.example.com"


@pytest.mark.asyncio
async def test_apis_guru_returns_empty_for_non_object_payload() -> None:
    adapter = ApisGuruAdapter()

    with patch("max.sources.apis_guru.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: ["not", "an", "object"])

        signals = await adapter.fetch(limit=10)

    assert signals == []
