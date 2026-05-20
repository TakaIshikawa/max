"""Tests for spec publication backlog aging reports."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from io import StringIO

import pytest

from max.analysis.spec_publication_backlog_aging import (
    KIND,
    SCHEMA_VERSION,
    build_spec_publication_backlog_aging,
    render_spec_publication_backlog_aging,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit


NOW = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)


def test_spec_publication_backlog_aging_ranks_overdue_before_recent(store: Store) -> None:
    _seed_backlog(store)

    report = build_spec_publication_backlog_aging(
        store,
        stale_after_hours=24,
        limit=20,
        now=NOW,
    )
    repeated = build_spec_publication_backlog_aging(
        store,
        stale_after_hours=24,
        limit=20,
        now=NOW,
    )

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert [item["idea_id"] for item in report["backlog_items"]] == [
        "idea-overdue",
        "idea-stale",
        "idea-fresh",
    ]
    assert report["age_bands"] == {
        "overdue": ["idea-overdue"],
        "stale": ["idea-stale"],
        "fresh": ["idea-fresh"],
    }
    assert report["summary"]["backlog_count"] == 3
    assert report["summary"]["overdue_count"] == 1
    assert report["summary"]["oldest_age_hours"] == 84
    assert report["summary"]["profiles"][0] == {
        "profile": "finops",
        "backlog_count": 2,
        "overdue_count": 1,
        "oldest_age_hours": 84,
    }
    assert report["backlog_items"][0]["priority"] == "p0"
    assert report["backlog_items"][0]["stale_band"] == "overdue"
    assert report["backlog_items"][1]["latest_publication_status"] == "failed"
    assert any("Publish or explicitly defer overdue specs first" in item for item in report["next_actions"])


def test_spec_publication_backlog_aging_excludes_published_and_rejected(store: Store) -> None:
    _seed_backlog(store)

    report = build_spec_publication_backlog_aging(store, stale_after_hours=24, limit=20, now=NOW)

    assert {item["idea_id"] for item in report["backlog_items"]} == {
        "idea-overdue",
        "idea-stale",
        "idea-fresh",
    }
    assert "idea-published-status" not in {item["idea_id"] for item in report["backlog_items"]}
    assert "idea-published-attempt" not in {item["idea_id"] for item in report["backlog_items"]}
    assert "idea-rejected" not in {item["idea_id"] for item in report["backlog_items"]}


def test_spec_publication_backlog_aging_empty_store_returns_guidance(store: Store) -> None:
    report = build_spec_publication_backlog_aging(store, now=NOW)

    assert report["backlog_items"] == []
    assert report["age_bands"] == {"overdue": [], "stale": [], "fresh": []}
    assert report["summary"]["backlog_count"] == 0
    assert report["next_actions"] == ["No approved unpublished ideas need publication follow-up."]


def test_render_spec_publication_backlog_aging_json_markdown_csv_and_invalid_format(
    store: Store,
) -> None:
    _seed_backlog(store)
    report = build_spec_publication_backlog_aging(store, stale_after_hours=24, limit=20, now=NOW)

    assert json.loads(render_spec_publication_backlog_aging(report, fmt="json")) == report

    markdown = render_spec_publication_backlog_aging(report, fmt="markdown")
    assert markdown.startswith("# Spec Publication Backlog Aging")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "| `idea-overdue` | p0 | overdue | 84 | `finops` | `finops` | `none` |" in markdown

    rendered_csv = render_spec_publication_backlog_aging(report, fmt="csv")
    rows = list(csv.DictReader(StringIO(rendered_csv)))
    assert rendered_csv.splitlines()[0] == (
        "idea_id,title,status,profile,domain,age_hours,stale_band,priority,created_at,"
        "latest_publication_status,latest_publication_at,recommendation"
    )
    assert [row["idea_id"] for row in rows] == ["idea-overdue", "idea-stale", "idea-fresh"]
    assert rows[0]["priority"] == "p0"
    assert rows[1]["latest_publication_status"] == "failed"

    with pytest.raises(ValueError, match="Unsupported spec publication backlog aging format: yaml"):
        render_spec_publication_backlog_aging(report, fmt="yaml")
    with pytest.raises(ValueError, match="stale_after_hours must be at least 1"):
        build_spec_publication_backlog_aging(store, stale_after_hours=0)
    with pytest.raises(ValueError, match="limit must be at least 1"):
        build_spec_publication_backlog_aging(store, limit=0)


def _seed_backlog(store: Store) -> None:
    _insert_unit(store, "idea-overdue", "approved", "finops", "2026-05-17T00:00:00+00:00")
    _insert_unit(store, "idea-stale", "approved", "finops", "2026-05-19T00:00:00+00:00")
    _insert_unit(store, "idea-fresh", "approved", "support", "2026-05-20T00:00:00+00:00")
    _insert_unit(store, "idea-published-status", "published", "finops", "2026-05-16T00:00:00+00:00")
    _insert_unit(store, "idea-published-attempt", "approved", "support", "2026-05-16T00:00:00+00:00")
    _insert_unit(store, "idea-rejected", "rejected", "support", "2026-05-16T00:00:00+00:00")
    store.insert_publication_attempt(
        idea_id="idea-stale",
        target_type="github",
        status="failed",
        response_status=500,
        error="server error",
    )
    store.insert_publication_attempt(
        idea_id="idea-published-attempt",
        target_type="github",
        status="published",
        response_status=201,
    )


def _insert_unit(store: Store, idea_id: str, status: str, domain: str, created_at: str) -> None:
    store.insert_buildable_unit(
        BuildableUnit(
            id=idea_id,
            title=idea_id,
            one_liner="one",
            category=BuildableCategory.CLI_TOOL,
            problem="problem",
            solution="solution",
            value_proposition="value",
            status=status,
            domain=domain,
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(created_at),
        )
    )
