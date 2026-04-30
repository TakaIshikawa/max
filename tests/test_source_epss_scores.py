"""Tests for the FIRST EPSS source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest

from max.sources.epss_scores import (
    FIRST_EPSS_API_URL,
    FIRST_EPSS_CVE_URL,
    EpssScoresAdapter,
    parse_epss_scores,
)
from max.sources.registry import get_adapter, get_adapter_metadata, list_adapters, reload_registry
from max.types.signal import SignalSourceType


MOCK_EPSS_PAYLOAD = {
    "status": "OK",
    "status-code": 200,
    "total": 3,
    "data": [
        {
            "cve": "CVE-2026-1111",
            "epss": "0.972240000",
            "percentile": "0.999990000",
            "date": "2026-04-28",
        },
        {
            "cve": "CVE-2026-2222",
            "epss": "0.812340000",
            "percentile": "0.970000000",
            "date": "2026-04-28",
        },
        {
            "cve": "CVE-2026-3333",
            "epss": "0.712340000",
            "percentile": "0.951000000",
            "created": "2026-04-27T02:30:00Z",
        },
    ],
}


def test_parse_epss_scores_maps_rows_to_signals() -> None:
    signals = parse_epss_scores(MOCK_EPSS_PAYLOAD, limit=10)

    assert [signal.id for signal in signals] == [
        "epss_scores:CVE-2026-1111:2026-04-28",
        "epss_scores:CVE-2026-2222:2026-04-28",
        "epss_scores:CVE-2026-3333:2026-04-27",
    ]

    signal = signals[0]
    assert signal.source_type == SignalSourceType.SECURITY
    assert signal.source_adapter == "epss_scores"
    assert signal.title == "FIRST EPSS CVE-2026-1111: 0.972 score (1.000 percentile)"
    assert signal.url == f"{FIRST_EPSS_CVE_URL}?id=CVE-2026-1111"
    assert signal.published_at == datetime(2026, 4, 28, tzinfo=timezone.utc)
    assert signal.credibility == 0.982
    assert "security" in signal.tags
    assert "epss" in signal.tags
    assert "exploit-likelihood" in signal.tags
    assert "critical-epss" in signal.tags
    assert "top-percentile" in signal.tags
    assert signal.metadata == {
        "cve_id": "CVE-2026-1111",
        "epss_score": 0.97224,
        "percentile": 0.99999,
        "observed_date": "2026-04-28",
        "source_url": FIRST_EPSS_API_URL,
        "signal_role": "problem",
    }
    assert "score 0.972240" in signal.content
    assert "Observed on 2026-04-28" in signal.content


def test_parse_epss_scores_enforces_limit_and_deduplicates_cves() -> None:
    payload = {
        "data": [
            MOCK_EPSS_PAYLOAD["data"][0],
            {**MOCK_EPSS_PAYLOAD["data"][0], "epss": "0.980000000"},
            MOCK_EPSS_PAYLOAD["data"][1],
        ],
    }

    signals = parse_epss_scores(payload, limit=2)

    assert [signal.metadata["cve_id"] for signal in signals] == [
        "CVE-2026-1111",
        "CVE-2026-2222",
    ]


def test_parse_epss_scores_skips_malformed_rows() -> None:
    payload = {
        "data": [
            {"cve": "", "epss": "0.9", "percentile": "0.99", "date": "2026-04-28"},
            {"cve": "not-a-cve", "epss": "0.9", "percentile": "0.99"},
            {"cve": "CVE-2026-4444", "epss": "bad", "percentile": "0.99"},
            {"cve": "CVE-2026-5555", "epss": "0.9", "percentile": "1.2"},
            ["not", "a", "row"],
            {
                "cve": "CVE-2026-6666",
                "epss": "0.900000000",
                "percentile": "0.990000000",
                "date": "not-a-date",
            },
        ],
    }

    signals = parse_epss_scores(payload, limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["cve_id"] == "CVE-2026-6666"
    assert signals[0].metadata["observed_date"] == ""
    assert signals[0].published_at is None


def test_parse_epss_scores_handles_malformed_payload_shape() -> None:
    assert parse_epss_scores([], limit=10) == []
    assert parse_epss_scores({}, limit=10) == []
    assert parse_epss_scores({"data": "bad"}, limit=10) == []


def test_epss_scores_adapter_properties() -> None:
    adapter = EpssScoresAdapter(
        config={
            "base_url": "https://example.test/epss",
            "min_epss": "0.8",
            "min_percentile": "0.98",
            "date": "2026-04-28",
        }
    )

    assert adapter.name == "epss_scores"
    assert adapter.source_type == SignalSourceType.SECURITY.value
    assert adapter.base_url == "https://example.test/epss"
    assert adapter.min_epss == 0.8
    assert adapter.min_percentile == 0.98
    assert adapter.date == "2026-04-28"


@pytest.mark.asyncio
async def test_epss_scores_adapter_fetch_success_with_injected_client() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=MOCK_EPSS_PAYLOAD, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = EpssScoresAdapter(
            config={"base_url": "https://example.test/epss", "date": "2026-04-28"},
            client=client,
        )
        signals = await adapter.fetch(limit=2)

    assert [signal.metadata["cve_id"] for signal in signals] == [
        "CVE-2026-1111",
        "CVE-2026-2222",
    ]
    assert len(requests) == 1
    assert requests[0].url.params["epss-gt"] == "0.7"
    assert requests[0].url.params["percentile-gt"] == "0.95"
    assert requests[0].url.params["order"] == "!epss"
    assert requests[0].url.params["limit"] == "2"
    assert requests[0].url.params["date"] == "2026-04-28"
    assert requests[0].headers["accept"] == "application/json"


@pytest.mark.asyncio
async def test_epss_scores_adapter_enforces_limit_parameter_for_fetch() -> None:
    observed_limits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_limits.append(request.url.params["limit"])
        return httpx.Response(200, json=MOCK_EPSS_PAYLOAD, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = EpssScoresAdapter(config={"base_url": "https://example.test/epss"}, client=client)
        signals = await adapter.fetch(limit=1)

    assert observed_limits == ["1"]
    assert [signal.metadata["cve_id"] for signal in signals] == ["CVE-2026-1111"]


@pytest.mark.asyncio
async def test_epss_scores_adapter_handles_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"message": "unavailable"}, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = EpssScoresAdapter(config={"base_url": "https://example.test/epss"}, client=client)
        signals = await adapter.fetch(limit=5)

    assert signals == []


@pytest.mark.asyncio
async def test_epss_scores_adapter_handles_network_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network unavailable", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = EpssScoresAdapter(config={"base_url": "https://example.test/epss"}, client=client)
        signals = await adapter.fetch(limit=5)

    assert signals == []


def test_epss_scores_registry_registration_and_metadata() -> None:
    with patch("max.config.MAX_ADAPTERS", "epss_scores"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        assert list_adapters() == ["epss_scores"]
        assert get_adapter("epss_scores").name == "epss_scores"
        metadata = get_adapter_metadata()["epss_scores"]

    assert metadata.config_keys == ["base_url", "min_epss", "min_percentile", "date"]
    assert metadata.required_keys == []
    assert "FIRST EPSS" in metadata.description

    reload_registry()
