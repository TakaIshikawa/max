"""Tests for retention cohort exports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from max.exports.retention_cohorts import (
    KIND,
    SCHEMA_VERSION,
    build_retention_cohort_export,
    render_retention_cohort_json,
    render_retention_cohort_markdown,
)
from max.types.signal import Signal, SignalSourceType


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _make_unit(
    *,
    unit_id: str,
    created_at: str,
    domain: str = "devtools",
    evidence_signals: list[str] | None = None,
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = f"Unit {unit_id}"
    unit.domain = domain
    unit.created_at = _dt(created_at)
    unit.updated_at = _dt(created_at)
    unit.evidence_signals = evidence_signals or []
    return unit


def _make_signal(
    *,
    signal_id: str,
    title: str,
    published_at: str,
) -> Signal:
    return Signal(
        id=signal_id,
        title=title,
        content=title,
        source_type=SignalSourceType.EXPERIMENT,
        source_adapter="validation",
        url=f"https://example.com/{signal_id}",
        published_at=_dt(published_at),
        fetched_at=_dt(published_at),
        metadata={"signal_role": "market"},
    )


def _mock_store(units: list[MagicMock], signals: list[Signal]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    store.get_signals.return_value = signals
    return store


def test_build_monthly_retention_cohorts_tracks_retained_expanded_and_dropped() -> None:
    units = [
        _make_unit(unit_id="bu-1", created_at="2026-01-05T00:00:00", evidence_signals=["sig-1", "sig-2"]),
        _make_unit(unit_id="bu-2", created_at="2026-01-20T00:00:00", evidence_signals=["sig-3"]),
    ]
    signals = [
        _make_signal(signal_id="sig-1", title="Initial validation", published_at="2026-01-07T00:00:00"),
        _make_signal(signal_id="sig-2", title="Expansion interview", published_at="2026-02-02T00:00:00"),
        _make_signal(signal_id="sig-3", title="Second unit validation", published_at="2026-01-25T00:00:00"),
    ]
    store = _mock_store(units, signals)

    report = build_retention_cohort_export(store, period="month")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["source"]["period"] == "month"
    assert len(report["cohorts"]) == 1
    cohort = report["cohorts"][0]
    assert cohort["cohort"] == "2026-01"
    assert cohort["unit_count"] == 2
    assert cohort["evidence_signal_count"] == 3
    assert cohort["activity"][0]["retention_pct"] == 100.0
    assert cohort["activity"][1]["retention_pct"] == 50.0
    assert cohort["activity"][1]["retained_units"] == 1
    assert cohort["activity"][1]["expanded_units"] == 1
    assert cohort["activity"][1]["dropped_units"] == 1
    assert cohort["expansion_signals"][0]["title"] == "Expansion interview"


def test_build_weekly_retention_cohorts_uses_iso_week_labels_and_sparse_weeks() -> None:
    units = [
        _make_unit(unit_id="bu-1", created_at="2026-03-03T00:00:00", evidence_signals=["sig-1", "sig-2"]),
    ]
    signals = [
        _make_signal(signal_id="sig-1", title="Week one evidence", published_at="2026-03-04T00:00:00"),
        _make_signal(signal_id="sig-2", title="Week three evidence", published_at="2026-03-18T00:00:00"),
    ]
    store = _mock_store(units, signals)

    report = build_retention_cohort_export(store, period="week")

    cohort = report["cohorts"][0]
    assert cohort["cohort"] == "2026-W10"
    assert [row["period"] for row in cohort["activity"]] == ["2026-W10", "2026-W11", "2026-W12"]
    assert cohort["activity"][1]["active_units"] == 0
    assert cohort["activity"][1]["dropped_units"] == 1
    assert cohort["activity"][2]["expanded_units"] == 1


def test_domain_filter_is_passed_to_store_and_report_source() -> None:
    store = _mock_store([], [])

    report = build_retention_cohort_export(store, domain="ai", period="month")

    store.get_buildable_units.assert_called_once_with(limit=1000, domain="ai")
    assert report["source"]["domain_filter"] == "ai"


def test_empty_store_returns_actionable_empty_report() -> None:
    store = _mock_store([], [])

    report = build_retention_cohort_export(store)
    markdown = render_retention_cohort_markdown(report)
    rendered_json = render_retention_cohort_json(report)

    assert report["cohorts"] == []
    assert report["summary"]["cohort_count"] == 0
    assert "No retention cohorts are available yet" in report["summary"]["narrative"]
    assert "No cohorts available" in markdown
    assert json.loads(rendered_json)["cohorts"] == []


def test_json_renderer_is_stable_and_sorted() -> None:
    store = _mock_store([], [])
    report = build_retention_cohort_export(store)

    rendered = render_retention_cohort_json(report)

    assert rendered == render_retention_cohort_json(report)
    assert json.loads(rendered)["schema_version"] == SCHEMA_VERSION


def test_invalid_period_raises_value_error() -> None:
    store = _mock_store([], [])

    with pytest.raises(ValueError, match="period must be"):
        build_retention_cohort_export(store, period="quarter")
