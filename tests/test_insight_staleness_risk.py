from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest

from max.analysis.insight_staleness_risk import (
    KIND,
    SCHEMA_VERSION,
    build_insight_staleness_risk_report,
    render_insight_staleness_risk_report,
)
from max.store.db import Store
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


NOW = datetime(2026, 5, 20, tzinfo=UTC)


def test_insight_staleness_risk_report_ranks_stale_quiet_and_healthy(store: Store) -> None:
    _seed_insight_staleness(store)

    report = build_insight_staleness_risk_report(
        store,
        stale_after_days=45,
        quiet_after_days=21,
        now=NOW,
    )
    repeated = build_insight_staleness_risk_report(
        store,
        stale_after_days=45,
        quiet_after_days=21,
        now=NOW,
    )

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"] == {
        "insight_count": 3,
        "high_risk_count": 1,
        "moderate_risk_count": 1,
        "healthy_count": 1,
        "stale_or_quiet_count": 2,
    }
    assert [row["insight_id"] for row in report["rows"]] == [
        "ins-stale",
        "ins-quiet-recent",
        "ins-healthy",
    ]
    rows = {row["insight_id"]: row for row in report["rows"]}
    assert rows["ins-stale"]["profile"] == "enterprise"
    assert rows["ins-stale"]["domain"] == "security"
    assert rows["ins-stale"]["evidence_count"] == 2
    assert rows["ins-stale"]["insight_age_days"] == 70
    assert rows["ins-stale"]["newest_evidence_age_days"] == 31
    assert rows["ins-stale"]["risk_band"] == "high"
    assert rows["ins-stale"]["risk_reasons"] == ["stale_insight", "quiet_evidence_stream"]

    assert rows["ins-quiet-recent"]["risk_band"] == "moderate"
    assert rows["ins-quiet-recent"]["insight_age_days"] == 5
    assert rows["ins-quiet-recent"]["newest_evidence_age_days"] == 30
    assert rows["ins-quiet-recent"]["risk_reasons"] == ["quiet_evidence_stream"]

    assert rows["ins-healthy"]["risk_band"] == "healthy"
    assert rows["ins-healthy"]["newest_evidence_age_days"] == 2
    assert rows["ins-healthy"]["risk_reasons"] == []
    assert report["next_actions"] == [
        "Refresh or retire 1 high-risk stale insight(s) before using them for synthesis.",
        "Review 1 moderate-risk insight(s) for missing or quiet supporting evidence.",
    ]


def test_insight_staleness_risk_report_empty_input(store: Store) -> None:
    report = build_insight_staleness_risk_report(store, now=NOW)

    assert report["summary"]["insight_count"] == 0
    assert report["rows"] == []
    assert report["stale_or_quiet_insights"] == []
    assert report["next_actions"] == [
        "All analyzed insights have recent creation and supporting evidence timestamps."
    ]


def test_render_insight_staleness_risk_report_json_markdown_csv_and_invalid_format(store: Store) -> None:
    _seed_insight_staleness(store)
    report = build_insight_staleness_risk_report(store, stale_after_days=45, quiet_after_days=21, now=NOW)

    assert json.loads(render_insight_staleness_risk_report(report, fmt="json")) == report

    markdown = render_insight_staleness_risk_report(report, fmt="markdown")
    assert markdown.startswith("# Insight Staleness Risk")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert markdown.index("| `ins-stale` |") < markdown.index("| `ins-quiet-recent` |")
    assert markdown.index("| `ins-quiet-recent` |") < markdown.index("| `ins-healthy` |")

    rendered_csv = render_insight_staleness_risk_report(report, fmt="csv")
    assert rendered_csv.splitlines()[0] == (
        "insight_id,profile,domain,evidence_count,insight_age_days,"
        "newest_evidence_age_days,risk_band,risk_reasons"
    )
    rows = list(csv.DictReader(StringIO(rendered_csv)))
    assert [row["insight_id"] for row in rows] == ["ins-stale", "ins-quiet-recent", "ins-healthy"]
    assert rows[0]["risk_band"] == "high"
    assert rows[0]["risk_reasons"] == "stale_insight; quiet_evidence_stream"

    with pytest.raises(ValueError, match="Unsupported insight staleness risk report format: yaml"):
        render_insight_staleness_risk_report(report, fmt="yaml")


def test_insight_staleness_risk_report_validates_arguments(store: Store) -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        build_insight_staleness_risk_report(store, limit=0)
    with pytest.raises(ValueError, match="stale_after_days must be at least 1"):
        build_insight_staleness_risk_report(store, stale_after_days=0)
    with pytest.raises(ValueError, match="quiet_after_days must be at least 1"):
        build_insight_staleness_risk_report(store, quiet_after_days=0)


def _seed_insight_staleness(store: Store) -> None:
    store.insert_signal(_signal("sig-stale-old", 50, "enterprise"))
    store.insert_signal(_signal("sig-stale-newest", 31, "enterprise"))
    store.insert_signal(_signal("sig-quiet", 30, "growth"))
    store.insert_signal(_signal("sig-healthy", 2, "growth"))
    store.insert_insight(_insight("ins-stale", 70, ["sig-stale-old", "sig-stale-newest"], ["security"]))
    store.insert_insight(_insight("ins-quiet-recent", 5, ["sig-quiet"], ["ai"]))
    store.insert_insight(_insight("ins-healthy", 4, ["sig-healthy"], ["ai"]))


def _signal(signal_id: str, age_days: int, profile: str) -> Signal:
    fetched_at = NOW - timedelta(days=age_days)
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FORUM,
        source_adapter="test",
        title=signal_id,
        content="content",
        url=f"https://example.com/{signal_id}",
        fetched_at=fetched_at,
        metadata={"profile": profile},
    )


def _insight(insight_id: str, age_days: int, evidence: list[str], domains: list[str]) -> Insight:
    return Insight(
        id=insight_id,
        category=InsightCategory.GAP,
        title=insight_id,
        summary="summary",
        evidence=evidence,
        domains=domains,
        created_at=NOW - timedelta(days=age_days),
    )
