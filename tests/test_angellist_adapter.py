"""Tests for AngelList import adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.angellist_adapter import AngelListAdapter, _parse_dt
from max.types.signal import SignalSourceType


MOCK_ANGELLIST_RESPONSE = {
    "startups": [
        {
            "id": 42,
            "name": "VectorOps",
            "slug": "vectorops",
            "product_desc": "Vector observability for AI engineering teams.",
            "angellist_url": "https://angel.co/company/vectorops",
            "team_size": 28,
            "technology_tags": [{"name": "Python"}, {"name": "Kubernetes"}],
            "markets": [{"name": "Developer Tools"}],
            "funding": {
                "total_raised_usd": 12_000_000,
                "last_round_at": "2026-03-01T00:00:00Z",
                "rounds": [{"type": "seed", "amount_usd": 12_000_000}],
            },
            "jobs": [{"title": "Founding Infrastructure Engineer"}, {"title": "AI Product Lead"}],
        }
    ]
}


def _mock_response(payload: dict) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    return resp


def test_parse_dt() -> None:
    parsed = _parse_dt("2026-03-01T00:00:00Z")
    assert parsed is not None
    assert parsed.year == 2026


def test_adapter_config() -> None:
    adapter = AngelListAdapter(config={"markets": ["ai"]})
    assert adapter.name == "angellist_import"
    assert adapter.source_type == SignalSourceType.FUNDING.value
    assert adapter.markets == ["ai"]


@pytest.mark.asyncio
async def test_fetch_returns_empty_without_token() -> None:
    with patch("max.imports.angellist_adapter._get_token", return_value=None):
        assert await AngelListAdapter().fetch(limit=5) == []


@pytest.mark.asyncio
async def test_fetch_parses_startup_profiles() -> None:
    adapter = AngelListAdapter(config={"markets": ["developer-tools"]})
    with (
        patch("max.imports.angellist_adapter._get_token", return_value="token"),
        patch("max.imports.angellist_adapter.fetch_with_retry", new_callable=AsyncMock) as fetch,
    ):
        fetch.return_value = _mock_response(MOCK_ANGELLIST_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "VectorOps"
    assert signal.source_type == SignalSourceType.FUNDING
    assert "developer-tools" in signal.tags
    assert "python" in signal.tags
    assert signal.metadata["team_size"] == 28
    assert signal.metadata["total_raised_usd"] == 12_000_000
    assert signal.metadata["job_count"] == 2
    assert signal.metadata["hiring_roles"] == ["Founding Infrastructure Engineer", "AI Product Lead"]
    assert signal.metadata["trend_signals"]["well_funded"] is True
    assert signal.metadata["trend_signals"]["actively_hiring"] is True


@pytest.mark.asyncio
async def test_fetch_parses_alternate_funding_and_jobs_shape() -> None:
    adapter = AngelListAdapter(config={"markets": ["ai"]})
    payload = {
        "companies": [
            {
                "slug": "agentgrid",
                "name": "AgentGrid",
                "high_concept": "Agent orchestration for operations teams.",
                "url": "https://angel.co/company/agentgrid",
                "company_size": "11-50",
                "technologies": ["Python", {"name": "Postgres"}],
                "funding_rounds": [
                    {"type": "pre_seed", "amount_usd": "500000"},
                    {"type": "seed", "raised_amount_usd": 2500000},
                ],
                "job_postings": ["Founding GTM Engineer"],
                "updated_at": "2026-02-10T12:00:00Z",
            }
        ]
    }

    with (
        patch("max.imports.angellist_adapter._get_token", return_value="token"),
        patch("max.imports.angellist_adapter.fetch_with_retry", new_callable=AsyncMock) as fetch,
    ):
        fetch.return_value = _mock_response(payload)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "AgentGrid"
    assert signal.metadata["team_size"] == "11-50"
    assert signal.metadata["technology_tags"] == ["Python", "Postgres"]
    assert signal.metadata["total_raised_usd"] == 3_000_000
    assert signal.metadata["job_count"] == 1
    assert signal.metadata["hiring_roles"] == ["Founding GTM Engineer"]


@pytest.mark.asyncio
async def test_fetch_deduplicates() -> None:
    adapter = AngelListAdapter(config={"markets": ["ai"]})
    payload = {"startups": [MOCK_ANGELLIST_RESPONSE["startups"][0], MOCK_ANGELLIST_RESPONSE["startups"][0]]}
    with (
        patch("max.imports.angellist_adapter._get_token", return_value="token"),
        patch("max.imports.angellist_adapter.fetch_with_retry", new_callable=AsyncMock) as fetch,
    ):
        fetch.return_value = _mock_response(payload)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = AngelListAdapter(config={"markets": ["ai"]})
    with (
        patch("max.imports.angellist_adapter._get_token", return_value="token"),
        patch("max.imports.angellist_adapter.fetch_with_retry", new_callable=AsyncMock) as fetch,
    ):
        fetch.side_effect = Exception("boom")
        assert await adapter.fetch(limit=10) == []
