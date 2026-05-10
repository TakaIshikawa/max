"""Tests for Crunchbase import adapter — company funding data collection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.crunchbase_adapter import (
    CrunchbaseAdapter,
    _build_tags,
    _parse_dt,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_CB_RESPONSE = {
    "entities": [
        {
            "properties": {
                "identifier": {"value": "OpenAI", "permalink": "openai"},
                "short_description": "AI research and deployment company",
                "funding_total": {"value_usd": 11_000_000_000},
                "num_funding_rounds": 7,
                "last_funding_at": "2024-02-15",
                "last_funding_type": "series_unknown",
                "num_employees_enum": "c_01001_05000",
                "founded_on": "2015-12-11",
                "categories": [
                    {"value": "artificial-intelligence"},
                    {"value": "machine-learning"},
                ],
                "location_identifiers": [{"value": "San Francisco"}],
                "rank_org": 5,
            }
        },
        {
            "properties": {
                "identifier": {"value": "Anthropic", "permalink": "anthropic"},
                "short_description": "AI safety company",
                "funding_total": {"value_usd": 7_000_000_000},
                "num_funding_rounds": 5,
                "last_funding_at": "2024-03-01",
                "last_funding_type": "series_c",
                "num_employees_enum": "c_00501_01000",
                "founded_on": "2021-01-01",
                "categories": [{"value": "artificial-intelligence"}],
                "location_identifiers": [{"value": "San Francisco"}],
                "rank_org": 15,
            }
        },
    ]
}

MOCK_CB_EMPTY = {"entities": []}


def _mock_response(payload: dict, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


# ── Unit tests ───────────────────────────────────────────────────────


def test_parse_dt_iso() -> None:
    dt = _parse_dt("2024-02-15T10:00:00Z")
    assert dt is not None
    assert dt.year == 2024


def test_parse_dt_date_only() -> None:
    dt = _parse_dt("2024-02-15")
    assert dt is not None
    assert dt.month == 2
    assert dt.day == 15


def test_parse_dt_none() -> None:
    assert _parse_dt(None) is None
    assert _parse_dt("") is None


def test_build_tags_known_categories() -> None:
    tags = _build_tags(["artificial-intelligence", "machine-learning"], "developer-tools")
    assert "ai" in tags
    assert "ml" in tags
    assert "devtools" in tags
    assert "crunchbase" in tags


def test_build_tags_unknown_category() -> None:
    tags = _build_tags(["quantum-computing"], "saas")
    assert "quantum-computing" in tags
    assert "saas" in tags


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = CrunchbaseAdapter()
    assert adapter.name == "crunchbase_import"


def test_adapter_source_type() -> None:
    adapter = CrunchbaseAdapter()
    assert adapter.source_type == SignalSourceType.FUNDING.value


def test_adapter_default_categories() -> None:
    adapter = CrunchbaseAdapter()
    assert "artificial-intelligence" in adapter.categories


def test_adapter_custom_categories() -> None:
    adapter = CrunchbaseAdapter(config={"categories": ["fintech"]})
    assert adapter.categories == ["fintech"]


# ── Fetch tests with mocked API ─────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_returns_empty_without_key() -> None:
    adapter = CrunchbaseAdapter()

    with patch("max.imports.crunchbase_adapter._get_api_key", return_value=None):
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_parses_organizations() -> None:
    adapter = CrunchbaseAdapter(config={"categories": ["artificial-intelligence"]})

    with (
        patch("max.imports.crunchbase_adapter._get_api_key", return_value="test-key"),
        patch(
            "max.imports.crunchbase_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = _mock_response(MOCK_CB_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    sig = signals[0]
    assert sig.title == "OpenAI"
    assert sig.source_adapter == "crunchbase_import"
    assert sig.source_type == SignalSourceType.FUNDING
    assert "openai" in sig.url
    assert sig.metadata["total_funding_usd"] == 11_000_000_000
    assert sig.metadata["num_funding_rounds"] == 7
    assert sig.metadata["location"] == "San Francisco"


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = CrunchbaseAdapter(config={"categories": ["ai"]})

    with (
        patch("max.imports.crunchbase_adapter._get_api_key", return_value="test-key"),
        patch(
            "max.imports.crunchbase_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = _mock_response(MOCK_CB_RESPONSE)
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_deduplicates() -> None:
    dup = {"entities": [MOCK_CB_RESPONSE["entities"][0], MOCK_CB_RESPONSE["entities"][0]]}
    adapter = CrunchbaseAdapter(config={"categories": ["ai"]})

    with (
        patch("max.imports.crunchbase_adapter._get_api_key", return_value="test-key"),
        patch(
            "max.imports.crunchbase_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = _mock_response(dup)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = CrunchbaseAdapter(config={"categories": ["ai"]})

    with (
        patch("max.imports.crunchbase_adapter._get_api_key", return_value="test-key"),
        patch(
            "max.imports.crunchbase_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.side_effect = Exception("API error")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_empty_response() -> None:
    adapter = CrunchbaseAdapter(config={"categories": ["ai"]})

    with (
        patch("max.imports.crunchbase_adapter._get_api_key", return_value="test-key"),
        patch(
            "max.imports.crunchbase_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = _mock_response(MOCK_CB_EMPTY)
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_credibility_from_funding() -> None:
    adapter = CrunchbaseAdapter(config={"categories": ["ai"]})

    with (
        patch("max.imports.crunchbase_adapter._get_api_key", return_value="test-key"),
        patch(
            "max.imports.crunchbase_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = _mock_response(MOCK_CB_RESPONSE)
        signals = await adapter.fetch(limit=10)

    # OpenAI: 11B / 100M = 110, capped at 1.0
    assert signals[0].credibility == 1.0
    # Anthropic: 7B / 100M = 70, capped at 1.0
    assert signals[1].credibility == 1.0
