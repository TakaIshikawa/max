"""Tests for the IETF Datatracker source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.ietf_datatracker import DEFAULT_BASE_URL, DOCUMENT_ENDPOINT, IetfDatatrackerAdapter
from max.types.signal import SignalSourceType


MOCK_DOCUMENTS = {
    "objects": [
        {
            "name": "draft-ietf-httpbis-safe-method-w-body",
            "title": "The HTTP QUERY Method",
            "abstract": "Defines a safe HTTP method with request content for API query workloads.",
            "time": "2025-03-01T10:11:12Z",
            "updated": "2025-03-08T00:00:00Z",
            "states": [{"slug": "active", "name": "Active"}],
            "stream": {"slug": "ietf", "name": "IETF"},
            "area": {"acronym": "art", "name": "Applications and Real-Time"},
            "group": {"acronym": "httpbis", "name": "HTTP"},
        },
        {
            "name": "draft-ietf-httpbis-safe-method-w-body",
            "title": "Duplicate HTTP QUERY Method",
            "abstract": "Duplicate record should be collapsed by canonical URL.",
            "time": "2025-03-09T00:00:00Z",
            "states": [{"slug": "active"}],
            "stream": {"slug": "ietf"},
            "area": {"acronym": "art"},
            "group": {"acronym": "httpbis"},
        },
        {
            "name": "draft-ietf-oauth-resource-metadata",
            "title": "OAuth Protected Resource Metadata",
            "abstract": "Discovery metadata for OAuth protected resources.",
            "time": "2025-02-01",
            "states": [{"slug": "active"}],
            "stream": {"slug": "ietf"},
            "area": {"acronym": "sec"},
            "group": {"acronym": "oauth"},
        },
        {
            "name": "draft-irtf-cfrg-unrelated",
            "title": "Unrelated Research Stream Draft",
            "abstract": "Research group activity that does not match configured filters.",
            "time": "2025-01-01",
            "states": [{"slug": "active"}],
            "stream": {"slug": "irtf"},
            "area": {"acronym": "sec"},
            "group": {"acronym": "cfrg"},
        },
    ]
}


def test_ietf_datatracker_adapter_properties() -> None:
    adapter = IetfDatatrackerAdapter()

    assert adapter.name == "ietf_datatracker"
    assert adapter.source_type == SignalSourceType.ROADMAP.value
    assert adapter.base_url == DEFAULT_BASE_URL
    assert adapter.keywords == []
    assert adapter.streams == []
    assert adapter.statuses == []
    assert adapter.max_results == 100


def test_ietf_datatracker_adapter_custom_config() -> None:
    adapter = IetfDatatrackerAdapter(
        config={
            "base_url": "https://datatracker.example.test/",
            "keywords": ["oauth"],
            "streams": ["ietf"],
            "statuses": ["active"],
            "watchlist_terms": ["http query"],
            "max_results": "12",
        }
    )

    assert adapter.base_url == "https://datatracker.example.test"
    assert adapter.keywords == ["oauth", "http query"]
    assert adapter.streams == ["ietf"]
    assert adapter.statuses == ["active"]
    assert adapter.max_results == 12


@pytest.mark.asyncio
async def test_ietf_datatracker_fetch_filters_dedupes_and_bounds_signals() -> None:
    adapter = IetfDatatrackerAdapter(
        config={
            "keywords": ["http query", "oauth"],
            "streams": ["ietf"],
            "statuses": ["active"],
            "max_results": 10,
        }
    )

    with patch("max.sources.ietf_datatracker.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_DOCUMENTS)

        signals = await adapter.fetch(limit=2)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == f"{DEFAULT_BASE_URL}{DOCUMENT_ENDPOINT}"
    assert mock_fetch.call_args.kwargs["params"] == {
        "format": "json",
        "limit": "6",
        "order_by": "-time",
    }
    assert [signal.source_adapter for signal in signals] == ["ietf_datatracker", "ietf_datatracker"]
    assert [signal.metadata["document_name"] for signal in signals] == [
        "draft-ietf-httpbis-safe-method-w-body",
        "draft-ietf-oauth-resource-metadata",
    ]
    assert len({signal.url for signal in signals}) == 2


@pytest.mark.asyncio
async def test_ietf_datatracker_signal_preserves_document_metadata() -> None:
    adapter = IetfDatatrackerAdapter(config={"keywords": ["http query"]})

    with patch("max.sources.ietf_datatracker.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_DOCUMENTS)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id.startswith("ietf_datatracker:")
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "ietf_datatracker"
    assert signal.title == "draft-ietf-httpbis-safe-method-w-body: The HTTP QUERY Method"
    assert signal.content == (
        "Defines a safe HTTP method with request content for API query workloads."
    )
    assert signal.url == (
        "https://datatracker.ietf.org/doc/draft-ietf-httpbis-safe-method-w-body/"
    )
    assert signal.published_at == datetime(2025, 3, 8, tzinfo=timezone.utc)
    assert signal.metadata["document_name"] == "draft-ietf-httpbis-safe-method-w-body"
    assert signal.metadata["status"] == "active"
    assert signal.metadata["stream"] == "ietf"
    assert signal.metadata["area"] == "art"
    assert signal.metadata["group"] == "httpbis"
    assert signal.metadata["published"] == "2025-03-01T10:11:12Z"
    assert signal.metadata["updated"] == "2025-03-08T00:00:00Z"
    assert signal.metadata["matched_keyword"] == "http query"
    assert "ietf" in signal.tags
    assert "standards" in signal.tags
    assert "http query" in signal.tags


@pytest.mark.asyncio
async def test_ietf_datatracker_handles_list_payload_and_resource_uri_metadata() -> None:
    adapter = IetfDatatrackerAdapter(config={"streams": ["ietf"], "statuses": ["rfc"]})
    payload = [
        {
            "name": "rfc9110",
            "title": "HTTP Semantics",
            "abstract": "Defines HTTP semantics.",
            "time": "2022-06-01",
            "state": "/api/v1/doc/state/rfc/",
            "stream": "/api/v1/name/doctagname/ietf/",
            "area": {"resource_uri": "/api/v1/group/area/art/"},
            "group": {"resource_uri": "/api/v1/group/group/httpbis/"},
            "html_url": "https://datatracker.ietf.org/doc/rfc9110/",
        }
    ]

    with patch("max.sources.ietf_datatracker.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: payload)

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert signals[0].metadata["status"] == "rfc"
    assert signals[0].metadata["stream"] == "ietf"
    assert signals[0].metadata["area"] == "art"
    assert signals[0].metadata["group"] == "httpbis"
    assert signals[0].credibility == 0.75


@pytest.mark.asyncio
async def test_ietf_datatracker_returns_empty_for_malformed_payload() -> None:
    adapter = IetfDatatrackerAdapter()

    with patch("max.sources.ietf_datatracker.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"meta": {"total_count": 0}})

        signals = await adapter.fetch(limit=10)

    assert signals == []
