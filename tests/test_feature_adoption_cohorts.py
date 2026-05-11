"""Tests for feature adoption cohort exports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from max.exports.feature_adoption_cohorts import (
    KIND,
    SCHEMA_VERSION,
    build_feature_adoption_cohorts_export,
    render_feature_adoption_cohorts_json,
    render_feature_adoption_cohorts_markdown,
)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _make_unit(
    *,
    unit_id: str = "bu-001",
    title: str = "Activation Dashboard",
    created_at: str = "2026-05-01T00:00:00",
    metadata: dict | None = None,
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.created_at = _dt(created_at)
    unit.updated_at = _dt(created_at)
    unit.metadata = metadata or {}
    return unit


def _mock_store(units: list[MagicMock] | None = None) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    return store


def test_build_schema_source_and_domain_filter() -> None:
    store = _mock_store([_make_unit()])

    report = build_feature_adoption_cohorts_export(store, domain="growth", period="month")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert "generated_at" in report
    assert report["source"]["entity_type"] == "feature_adoption_cohorts"
    assert report["source"]["domain_filter"] == "growth"
    assert report["source"]["period"] == "month"
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="growth")


def test_monthly_cohorts_group_by_period_feature_and_segment() -> None:
    report = build_feature_adoption_cohorts_export(
        _mock_store([
            _make_unit(
                unit_id="bu-2",
                title="Beta Invitations",
                metadata={
                    "feature_name": "Team Invites",
                    "launched_at": "2026-04-20T00:00:00Z",
                    "eligible_users": 50,
                    "activated_users": 25,
                    "retained_users": 10,
                    "segment": "smb",
                },
            ),
            _make_unit(
                unit_id="bu-1",
                title="Enterprise Invitations",
                metadata={
                    "feature_name": "Team Invites",
                    "launched_at": "2026-04-03T00:00:00Z",
                    "eligible_users": 100,
                    "activated_users": 80,
                    "retained_users": 60,
                    "segment": "enterprise",
                },
            ),
            _make_unit(
                unit_id="bu-3",
                title="Invite Templates",
                metadata={
                    "feature_name": "Team Invites",
                    "launched_at": "2026-04-18T00:00:00Z",
                    "eligible_users": "20",
                    "activated_users": "10",
                    "retained_users": "5",
                    "segment": "smb",
                },
            ),
        ])
    )

    assert [cohort["segment"] for cohort in report["cohorts"]] == ["enterprise", "smb"]
    enterprise, smb = report["cohorts"]
    assert enterprise["period"] == "2026-04"
    assert enterprise["period_start"] == "2026-04-01"
    assert enterprise["feature_name"] == "Team Invites"
    assert enterprise["adoption_pct"] == 80.0
    assert enterprise["retention_pct"] == 75.0
    assert smb["eligible_users"] == 70
    assert smb["activated_users"] == 35
    assert smb["retained_users"] == 15
    assert smb["adoption_pct"] == 50.0
    assert smb["retention_pct"] == 42.9
    assert smb["idea_ids"] == ["bu-2", "bu-3"]
    assert report["summary"]["overall_adoption_pct"] == 67.6
    assert report["summary"]["overall_retention_pct"] == 65.2


def test_weekly_cohorts_use_iso_week_labels() -> None:
    report = build_feature_adoption_cohorts_export(
        _mock_store([
            _make_unit(
                unit_id="bu-1",
                metadata={
                    "feature_name": "Usage Alerts",
                    "launched_at": "2026-03-03T00:00:00Z",
                    "eligible_users": 10,
                    "activated_users": 5,
                    "retained_users": 4,
                    "segment": "enterprise",
                },
            ),
            _make_unit(
                unit_id="bu-2",
                metadata={
                    "feature_name": "Usage Alerts",
                    "launched_at": "2026-03-10T00:00:00Z",
                    "eligible_users": 20,
                    "activated_users": 4,
                    "retained_users": 2,
                    "segment": "enterprise",
                },
            ),
        ]),
        period="week",
    )

    assert [cohort["period"] for cohort in report["cohorts"]] == ["2026-W10", "2026-W11"]
    assert report["cohorts"][0]["period_start"] == "2026-03-02"
    assert report["cohorts"][1]["period_start"] == "2026-03-09"


def test_sparse_or_missing_metadata_defaults_to_zero_without_division_errors() -> None:
    report = build_feature_adoption_cohorts_export(
        _mock_store([
            _make_unit(
                unit_id="bu-1",
                title="Fallback Feature",
                created_at="2026-02-15T00:00:00",
                metadata={},
            ),
            _make_unit(
                unit_id="bu-2",
                metadata={
                    "feature_adoption": {
                        "launched_at": "2026-02-20T00:00:00Z",
                        "eligible_users": "-10",
                        "activated_users": "",
                        "retained_users": "not-a-number",
                    },
                    "segment": "",
                },
            ),
        ])
    )

    assert [cohort["feature_name"] for cohort in report["cohorts"]] == [
        "Activation Dashboard",
        "Fallback Feature",
    ]
    for cohort in report["cohorts"]:
        assert cohort["eligible_users"] == 0
        assert cohort["activated_users"] == 0
        assert cohort["retained_users"] == 0
        assert cohort["adoption_pct"] == 0.0
        assert cohort["retention_pct"] == 0.0
    assert report["summary"]["zero_eligible_cohort_count"] == 2


def test_empty_store_returns_actionable_empty_report() -> None:
    report = build_feature_adoption_cohorts_export(_mock_store())
    markdown = render_feature_adoption_cohorts_markdown(report)
    rendered_json = render_feature_adoption_cohorts_json(report)

    assert report["cohorts"] == []
    assert report["summary"]["cohort_count"] == 0
    assert "No feature adoption cohorts are available yet" in report["summary"]["narrative"]
    assert "No feature adoption cohorts available" in markdown
    assert json.loads(rendered_json)["cohorts"] == []


def test_invalid_period_raises_value_error() -> None:
    with pytest.raises(ValueError, match="period must be"):
        build_feature_adoption_cohorts_export(_mock_store(), period="quarter")


def test_markdown_and_json_renderers_are_deterministic() -> None:
    report = build_feature_adoption_cohorts_export(
        _mock_store([
            _make_unit(
                metadata={
                    "adoption": {
                        "launched_at": "2026-05-04T00:00:00Z",
                        "eligible_users": "200",
                        "activated_users": "100",
                        "retained_users": "75",
                    },
                    "feature_name": "Smart Routing",
                    "segment": "midmarket",
                }
            )
        ]),
        period="week",
    )

    markdown = render_feature_adoption_cohorts_markdown(report)
    rendered_json = render_feature_adoption_cohorts_json(report)

    assert "# Feature Adoption Cohorts" in markdown
    assert "## Summary" in markdown
    assert "## Cohort Table" in markdown
    assert "Smart Routing" in markdown
    assert markdown.endswith("\n")
    assert rendered_json == render_feature_adoption_cohorts_json(report)
    parsed = json.loads(rendered_json)
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert list(parsed.keys()) == sorted(parsed.keys())
