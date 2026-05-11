"""Tests for the app store reviews import adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from max.imports.app_store_reviews_adapter import (
    AppStoreReviewsAdapter,
    parse_csv_reviews,
    parse_json_reviews,
)
from max.types.signal import SignalSourceType


CSV_DATA = """\
author,stars,headline,review,app_version,locale,date,helpful
Ana,5,Great sync,Sync finally works,2.1,US,2026-04-01T10:00:00Z,8
Bo,2,Buggy,Crashes on launch,2.0,GB,2026-04-02,3
Bad,,No rating,Ignored,2.0,US,2026-04-03,0
"""


def test_parse_csv_reviews_accepts_aliases_and_skips_unusable_rows() -> None:
    rows = parse_csv_reviews(CSV_DATA)

    assert len(rows) == 2
    assert rows[0]["reviewer"] == "Ana"
    assert rows[0]["rating"] == 5
    assert rows[0]["body"] == "Sync finally works"
    assert rows[0]["helpful_count"] == 8


def test_parse_json_reviews_wrapped_and_invalid() -> None:
    rows = parse_json_reviews(
        """{"reviews":[{"user":"Cy","score":4,"text":"Fast support","version":"3.0"}]}"""
    )

    assert rows[0]["reviewer"] == "Cy"
    assert rows[0]["rating"] == 4
    assert parse_json_reviews("{") == []


@pytest.mark.asyncio
async def test_fetch_inline_reviews_filters_ratings_and_preserves_metadata() -> None:
    adapter = AppStoreReviewsAdapter(
        config={
            "data": [
                {"reviewer": "Ana", "rating": 5, "title": "Great", "body": "Love it", "country": "US"},
                {"reviewer": "Bo", "rating": 2, "title": "Bad", "body": "Crashes", "country": "GB"},
            ],
            "app_name": "MaxApp",
            "marketplace": "App Store",
            "min_rating": 4,
            "tags": ["mobile"],
        }
    )

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source_type == SignalSourceType.MARKETPLACE
    assert signal.source_adapter == "app_store_reviews"
    assert signal.title == "MaxApp: Great"
    assert signal.content == "Love it"
    assert {"app_store_review", "positive", "mobile", "app_store"}.issubset(signal.tags)
    assert signal.metadata["app_name"] == "MaxApp"
    assert signal.metadata["marketplace"] == "App Store"
    assert signal.metadata["rating"] == 5
    assert signal.metadata["country"] == "US"


@pytest.mark.asyncio
async def test_fetch_from_file_respects_limit(tmp_path: Path) -> None:
    path = tmp_path / "reviews.csv"
    path.write_text(CSV_DATA, encoding="utf-8")
    adapter = AppStoreReviewsAdapter(config={"files": [str(path)], "max_rating": 5})

    signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["reviewer"] == "Ana"


@pytest.mark.asyncio
async def test_fetch_handles_invalid_sources_and_zero_limit(tmp_path: Path) -> None:
    adapter = AppStoreReviewsAdapter(config={"files": [str(tmp_path / "missing.json")], "data": "bad"})

    assert await adapter.fetch(limit=0) == []
    assert await adapter.fetch(limit=10) == []
