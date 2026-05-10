"""Tests for Glassdoor import adapter — employer insights collection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.glassdoor_adapter import (
    GlassdoorAdapter,
    _build_tags,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_GD_RESPONSE = {
    "response": {
        "employers": [
            {
                "id": 9079,
                "name": "Google",
                "overallRating": 4.4,
                "ceo": {"pctApprove": 92},
                "recommendToFriendRating": 4.2,
                "numberOfRatings": 35000,
                "industry": "Internet",
                "sectorName": "Information Technology",
                "revenue": "$100 billion+",
                "size": "10000+",
                "compensationAndBenefitsRating": 4.5,
                "cultureAndValuesRating": 4.1,
                "workLifeBalanceRating": 4.0,
                "featuredReview": {
                    "attributionURL": "https://www.glassdoor.com/Reviews/Google-Reviews-E9079.htm",
                },
            },
            {
                "id": 1651,
                "name": "Microsoft",
                "overallRating": 4.2,
                "ceo": {"pctApprove": 96},
                "recommendToFriendRating": 4.0,
                "numberOfRatings": 42000,
                "industry": "Computer Hardware & Software",
                "sectorName": "Information Technology",
                "revenue": "$100 billion+",
                "size": "10000+",
                "compensationAndBenefitsRating": 4.3,
                "cultureAndValuesRating": 3.9,
                "workLifeBalanceRating": 4.1,
                "featuredReview": {
                    "attributionURL": "https://www.glassdoor.com/Reviews/Microsoft-Reviews-E1651.htm",
                },
            },
        ]
    }
}

MOCK_GD_EMPTY = {"response": {"employers": []}}


def _mock_response(payload: dict, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


# ── Unit tests ───────────────────────────────────────────────────────


def test_build_tags_known_industry() -> None:
    tags = _build_tags("Internet", "Information Technology")
    assert "internet" in tags
    assert "information-technology" in tags
    assert "glassdoor" in tags


def test_build_tags_none_values() -> None:
    tags = _build_tags(None, None)
    assert tags == ["glassdoor"]


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = GlassdoorAdapter()
    assert adapter.name == "glassdoor_import"


def test_adapter_source_type() -> None:
    adapter = GlassdoorAdapter()
    assert adapter.source_type == SignalSourceType.SURVEY.value


def test_adapter_default_employers() -> None:
    adapter = GlassdoorAdapter()
    assert "Google" in adapter.employers
    assert "Microsoft" in adapter.employers


def test_adapter_custom_employers() -> None:
    adapter = GlassdoorAdapter(config={"employers": ["Stripe", "Vercel"]})
    assert adapter.employers == ["Stripe", "Vercel"]


# ── Fetch tests with mocked API ─────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_returns_empty_without_credentials() -> None:
    adapter = GlassdoorAdapter()

    with patch(
        "max.imports.glassdoor_adapter._get_credentials",
        return_value=(None, None),
    ):
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_parses_employers() -> None:
    adapter = GlassdoorAdapter(config={"employers": ["Google"]})

    with (
        patch(
            "max.imports.glassdoor_adapter._get_credentials",
            return_value=("pid", "pkey"),
        ),
        patch(
            "max.imports.glassdoor_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = _mock_response(MOCK_GD_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    sig = signals[0]
    assert sig.title == "Google"
    assert sig.source_adapter == "glassdoor_import"
    assert sig.source_type == SignalSourceType.SURVEY
    assert sig.metadata["employer_id"] == 9079
    assert sig.metadata["overall_rating"] == 4.4
    assert sig.metadata["ceo_approval"] == 92
    assert sig.metadata["recommend_to_friend"] == 4.2
    assert sig.metadata["number_of_ratings"] == 35000


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = GlassdoorAdapter(config={"employers": ["Google"]})

    with (
        patch(
            "max.imports.glassdoor_adapter._get_credentials",
            return_value=("pid", "pkey"),
        ),
        patch(
            "max.imports.glassdoor_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = _mock_response(MOCK_GD_RESPONSE)
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_deduplicates() -> None:
    dup = {
        "response": {
            "employers": [
                MOCK_GD_RESPONSE["response"]["employers"][0],
                MOCK_GD_RESPONSE["response"]["employers"][0],
            ]
        }
    }
    adapter = GlassdoorAdapter(config={"employers": ["Google"]})

    with (
        patch(
            "max.imports.glassdoor_adapter._get_credentials",
            return_value=("pid", "pkey"),
        ),
        patch(
            "max.imports.glassdoor_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = _mock_response(dup)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = GlassdoorAdapter(config={"employers": ["Google"]})

    with (
        patch(
            "max.imports.glassdoor_adapter._get_credentials",
            return_value=("pid", "pkey"),
        ),
        patch(
            "max.imports.glassdoor_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.side_effect = Exception("API error")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_empty_response() -> None:
    adapter = GlassdoorAdapter(config={"employers": ["Google"]})

    with (
        patch(
            "max.imports.glassdoor_adapter._get_credentials",
            return_value=("pid", "pkey"),
        ),
        patch(
            "max.imports.glassdoor_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = _mock_response(MOCK_GD_EMPTY)
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_credibility_from_rating() -> None:
    adapter = GlassdoorAdapter(config={"employers": ["Google"]})

    with (
        patch(
            "max.imports.glassdoor_adapter._get_credentials",
            return_value=("pid", "pkey"),
        ),
        patch(
            "max.imports.glassdoor_adapter.fetch_with_retry",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = _mock_response(MOCK_GD_RESPONSE)
        signals = await adapter.fetch(limit=10)

    # Google: 4.4 / 5.0 = 0.88
    assert signals[0].credibility == pytest.approx(0.88)
