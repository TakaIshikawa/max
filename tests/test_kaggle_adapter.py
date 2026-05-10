"""Tests for Kaggle import adapter — dataset and competition signal collection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.kaggle_adapter import (
    KaggleAdapter,
    _build_tags,
    _parse_dt,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_DATASET = {
    "ref": "username/titanic-dataset",
    "title": "Titanic Dataset",
    "subtitle": "Classic dataset for ML beginners",
    "ownerName": "kaggle-user",
    "lastUpdated": "2026-04-20T12:00:00Z",
    "downloadCount": 50000,
    "voteCount": 1200,
    "viewCount": 200000,
    "totalBytes": 34567890,
    "usabilityRating": 0.88,
    "fileCount": 3,
    "licenseName": "CC0: Public Domain",
    "tags": [
        {"name": "classification"},
        {"name": "tabular"},
    ],
}

MOCK_DATASET_2 = {
    "ref": "user2/housing-prices",
    "title": "Housing Prices Dataset",
    "subtitle": "Predict house prices with regression",
    "ownerName": "data-scientist",
    "lastUpdated": "2026-03-15T08:00:00Z",
    "downloadCount": 30000,
    "voteCount": 800,
    "viewCount": 150000,
    "totalBytes": 12345678,
    "usabilityRating": 0.92,
    "fileCount": 2,
    "licenseName": "CC BY-SA 4.0",
    "tags": ["regression", "tabular"],
}

MOCK_COMPETITION = {
    "ref": "titanic",
    "title": "Titanic - Machine Learning from Disaster",
    "description": "Predict survival on the Titanic",
    "organizationName": "Kaggle",
    "enabledDate": "2024-01-01T00:00:00Z",
    "deadline": "2026-12-31T23:59:59Z",
    "reward": "$10,000",
    "teamCount": 15000,
    "maxTeamSize": 5,
    "evaluationMetric": "accuracy",
    "isKernelsSubmitEnabled": True,
    "tags": [{"name": "beginner"}, {"name": "binary classification"}],
}

MOCK_COMPETITION_2 = {
    "ref": "house-prices-advanced",
    "title": "House Prices - Advanced Regression",
    "description": "Predict sales prices with creative feature engineering",
    "organizationName": "Kaggle",
    "enabledDate": "2024-06-01T00:00:00Z",
    "deadline": "2026-12-31T23:59:59Z",
    "reward": "$0",
    "teamCount": 8000,
    "maxTeamSize": 5,
    "evaluationMetric": "rmse",
    "isKernelsSubmitEnabled": False,
    "tags": ["regression"],
}


def _mock_response(payload, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


# ── Unit tests ───────────────────────────────────────────────────────


def test_parse_dt_valid() -> None:
    dt = _parse_dt("2026-04-20T12:00:00+00:00")
    assert dt is not None
    assert dt.year == 2026


def test_parse_dt_zulu() -> None:
    dt = _parse_dt("2026-04-20T12:00:00Z")
    assert dt is not None


def test_parse_dt_none() -> None:
    assert _parse_dt(None) is None


def test_parse_dt_invalid() -> None:
    assert _parse_dt("not-a-date") is None


def test_build_tags_with_tags() -> None:
    tags = _build_tags(["classification", "tabular"], "dataset")
    assert "kaggle" in tags
    assert "dataset" in tags
    assert "classification" in tags
    assert "tabular" in tags


def test_build_tags_no_tags() -> None:
    tags = _build_tags(None, "competition")
    assert "kaggle" in tags
    assert "competition" in tags


def test_build_tags_empty_list() -> None:
    tags = _build_tags([], "dataset")
    assert tags == ["dataset", "kaggle"]


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = KaggleAdapter()
    assert adapter.name == "kaggle_import"


def test_adapter_source_type() -> None:
    adapter = KaggleAdapter()
    assert adapter.source_type == SignalSourceType.TRENDING.value


def test_adapter_default_categories() -> None:
    adapter = KaggleAdapter()
    assert "featured" in adapter.categories
    assert "research" in adapter.categories


def test_adapter_custom_categories() -> None:
    adapter = KaggleAdapter(config={"categories": ["getting-started"]})
    assert adapter.categories == ["getting-started"]


def test_adapter_search_query() -> None:
    adapter = KaggleAdapter(config={"search": "nlp"})
    assert adapter.search_query == "nlp"


def test_adapter_sort_by_default() -> None:
    adapter = KaggleAdapter()
    assert adapter.sort_by == "hottest"


def test_adapter_sort_by_custom() -> None:
    adapter = KaggleAdapter(config={"sort_by": "votes"})
    assert adapter.sort_by == "votes"


# ── Fetch tests with mocked API ──────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_datasets() -> None:
    adapter = KaggleAdapter()

    with patch(
        "max.imports.kaggle_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.kaggle_adapter._get_api_token",
        return_value=(None, None),
    ):
        # First call: datasets, subsequent calls: competitions
        mock_fetch.side_effect = [
            _mock_response([MOCK_DATASET, MOCK_DATASET_2]),
            _mock_response([MOCK_COMPETITION]),
            _mock_response([MOCK_COMPETITION_2]),
            _mock_response([]),
        ]
        signals = await adapter.fetch(limit=10)

    # Should have 2 datasets + competitions
    dataset_signals = [s for s in signals if s.metadata["kind"] == "dataset"]
    assert len(dataset_signals) == 2

    sig = dataset_signals[0]
    assert sig.title == "Titanic Dataset"
    assert sig.source_adapter == "kaggle_import"
    assert sig.source_type == SignalSourceType.TRENDING
    assert "kaggle" in sig.tags
    assert sig.metadata["download_count"] == 50000
    assert sig.metadata["vote_count"] == 1200
    assert sig.metadata["total_bytes"] == 34567890
    assert sig.metadata["tags"] == ["classification", "tabular"]


@pytest.mark.asyncio
async def test_fetch_competitions() -> None:
    adapter = KaggleAdapter(config={"categories": ["featured"]})

    with patch(
        "max.imports.kaggle_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.kaggle_adapter._get_api_token",
        return_value=(None, None),
    ):
        mock_fetch.side_effect = [
            _mock_response([]),  # datasets
            _mock_response([MOCK_COMPETITION]),  # competitions
        ]
        signals = await adapter.fetch(limit=10)

    comp_signals = [s for s in signals if s.metadata["kind"] == "competition"]
    assert len(comp_signals) == 1

    sig = comp_signals[0]
    assert sig.title == "Titanic - Machine Learning from Disaster"
    assert sig.metadata["deadline"] == "2026-12-31T23:59:59Z"
    assert sig.metadata["reward"] == "$10,000"
    assert sig.metadata["team_count"] == 15000
    assert sig.metadata["evaluation_metric"] == "accuracy"
    assert sig.metadata["is_kernels_submit_enabled"] is True
    assert "competition" in sig.tags


@pytest.mark.asyncio
async def test_fetch_with_search() -> None:
    adapter = KaggleAdapter(config={"search": "nlp", "categories": []})

    with patch(
        "max.imports.kaggle_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.kaggle_adapter._get_api_token",
        return_value=(None, None),
    ):
        mock_fetch.return_value = _mock_response([MOCK_DATASET])
        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert signals[0].title == "Titanic Dataset"
    # Verify search param was passed
    call_kwargs = mock_fetch.call_args_list[0]
    assert call_kwargs.kwargs.get("params", {}).get("search") == "nlp" or \
        call_kwargs[1].get("params", {}).get("search") == "nlp"


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = KaggleAdapter()

    with patch(
        "max.imports.kaggle_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.kaggle_adapter._get_api_token",
        return_value=(None, None),
    ):
        mock_fetch.side_effect = [
            _mock_response([MOCK_DATASET, MOCK_DATASET_2]),
            _mock_response([MOCK_COMPETITION]),
            _mock_response([]),
            _mock_response([]),
        ]
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_deduplicates() -> None:
    adapter = KaggleAdapter(config={"categories": []})

    with patch(
        "max.imports.kaggle_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.kaggle_adapter._get_api_token",
        return_value=(None, None),
    ):
        mock_fetch.return_value = _mock_response([MOCK_DATASET, MOCK_DATASET])
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = KaggleAdapter()

    with patch(
        "max.imports.kaggle_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.kaggle_adapter._get_api_token",
        return_value=(None, None),
    ):
        mock_fetch.side_effect = Exception("API error")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_with_auth() -> None:
    adapter = KaggleAdapter(config={"categories": []})

    with patch(
        "max.imports.kaggle_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.kaggle_adapter._get_api_token",
        return_value=("user", "key123"),
    ):
        mock_fetch.return_value = _mock_response([MOCK_DATASET])
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_empty_response() -> None:
    adapter = KaggleAdapter(config={"categories": []})

    with patch(
        "max.imports.kaggle_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.kaggle_adapter._get_api_token",
        return_value=(None, None),
    ):
        mock_fetch.return_value = _mock_response([])
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_dataset_string_tags() -> None:
    """Datasets with string tags (not dicts) are handled correctly."""
    adapter = KaggleAdapter(config={"categories": []})

    with patch(
        "max.imports.kaggle_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.kaggle_adapter._get_api_token",
        return_value=(None, None),
    ):
        mock_fetch.return_value = _mock_response([MOCK_DATASET_2])
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert "regression" in signals[0].metadata["tags"]


@pytest.mark.asyncio
async def test_dataset_metadata_fields() -> None:
    """Verify all expected metadata fields are extracted."""
    adapter = KaggleAdapter(config={"categories": []})

    with patch(
        "max.imports.kaggle_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch, patch(
        "max.imports.kaggle_adapter._get_api_token",
        return_value=(None, None),
    ):
        mock_fetch.return_value = _mock_response([MOCK_DATASET])
        signals = await adapter.fetch(limit=10)

    meta = signals[0].metadata
    assert meta["kind"] == "dataset"
    assert meta["download_count"] == 50000
    assert meta["vote_count"] == 1200
    assert meta["view_count"] == 200000
    assert meta["total_bytes"] == 34567890
    assert meta["usability_rating"] == 0.88
    assert meta["file_count"] == 3
    assert meta["license"] == "CC0: Public Domain"
