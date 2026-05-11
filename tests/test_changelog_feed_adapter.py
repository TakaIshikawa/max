"""Tests for the changelog feed import adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from max.imports.changelog_feed_adapter import (
    ChangelogFeedAdapter,
    parse_csv_changelog,
    parse_json_changelog,
    parse_jsonl_changelog,
)
from max.types.signal import SignalSourceType


CSV_DATA = """\
release,released_at,name,description,type,link,breaking,components
1.2.0,2026-04-10,Workflow updates,Faster approvals,feature,https://example.com/1.2,false,approvals;admin
1.1.0,2026-03-01,Old release,Earlier work,fix,,false,api
"""


def test_parse_csv_changelog_accepts_aliases() -> None:
    rows = parse_csv_changelog(CSV_DATA)

    assert len(rows) == 2
    assert rows[0]["version"] == "1.2.0"
    assert rows[0]["title"] == "Workflow updates"
    assert rows[0]["affected_features"] == ["approvals", "admin"]


def test_parse_json_and_jsonl_changelog() -> None:
    rows = parse_json_changelog(
        """{"releases":[{"tag":"2.0.0","published_at":"2026-05-01","headline":"API v2","breaking":true,"features":["api"]}]}"""
    )
    jsonl = parse_jsonl_changelog('{"version":"2.1.0","title":"Patch"}\nnot json\n')

    assert rows[0]["version"] == "2.0.0"
    assert rows[0]["breaking_change"] is True
    assert rows[0]["affected_features"] == ["api"]
    assert jsonl[0]["title"] == "Patch"
    assert parse_json_changelog("{") == []


@pytest.mark.asyncio
async def test_fetch_inline_applies_since_filter_and_metadata() -> None:
    adapter = ChangelogFeedAdapter(
        config={
            "data": [
                {"version": "1.0.0", "date": "2026-01-01", "title": "Old", "summary": "Skip"},
                {
                    "version": "1.2.0",
                    "date": "2026-04-10",
                    "title": "Workflow updates",
                    "summary": "Faster approvals",
                    "category": "Feature",
                    "breaking_change": True,
                    "affected_features": ["approvals"],
                },
            ],
            "product_name": "Max",
            "vendor": "Acme",
            "default_url": "https://example.com/changelog",
            "since": "2026-04-01",
            "tags": ["competitive"],
        }
    )

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "changelog_feed"
    assert signal.title == "Max: Workflow updates"
    assert signal.url == "https://example.com/changelog"
    assert {"changelog", "roadmap", "feature", "breaking_change", "competitive"}.issubset(signal.tags)
    assert signal.metadata["product_name"] == "Max"
    assert signal.metadata["vendor"] == "Acme"
    assert signal.metadata["version"] == "1.2.0"
    assert signal.metadata["affected_features"] == ["approvals"]


@pytest.mark.asyncio
async def test_fetch_from_jsonl_file_and_respects_limit(tmp_path: Path) -> None:
    path = tmp_path / "changelog.jsonl"
    path.write_text('{"version":"1.0","title":"One"}\n{"version":"1.1","title":"Two"}\n', encoding="utf-8")
    adapter = ChangelogFeedAdapter(config={"files": [str(path)]})

    signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["version"] == "1.0"


@pytest.mark.asyncio
async def test_fetch_handles_bad_files_and_zero_limit(tmp_path: Path) -> None:
    adapter = ChangelogFeedAdapter(config={"files": [str(tmp_path / "missing.csv")], "data": "bad"})

    assert await adapter.fetch(limit=0) == []
    assert await adapter.fetch(limit=10) == []
