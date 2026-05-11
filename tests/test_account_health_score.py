"""Tests for account health score exports."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.account_health_score import (
    KIND,
    SCHEMA_VERSION,
    build_account_health_score_export,
    render_account_health_score_json,
    render_account_health_score_markdown,
)


def _unit(
    *,
    unit_id: str = "idea-1",
    title: str = "Account Workspace",
    domain: str = "success",
    metadata: dict | None = None,
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.domain = domain
    unit.metadata = metadata or {}
    return unit


def _store(units: list[MagicMock] | None = None) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    return store


def test_builds_schema_source_and_domain_filter() -> None:
    store = _store([_unit(metadata={"account_name": "Acme"})])

    report = build_account_health_score_export(store, domain="enterprise")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["source"]["entity_type"] == "account_health_score"
    assert report["source"]["domain_filter"] == "enterprise"
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="enterprise")


def test_scores_healthy_watchlist_and_at_risk_accounts_with_drivers() -> None:
    report = build_account_health_score_export(
        _store([
            _unit(
                unit_id="healthy",
                metadata={
                    "account_name": "Zenith",
                    "usage_trend": "growth",
                    "support_ticket_count": 0,
                    "nps_score": 68,
                    "renewal_date": "2099-01-01",
                    "champion_status": "strong",
                    "open_risks": [],
                    "expansion_signal_count": 3,
                },
            ),
            _unit(
                unit_id="watch",
                metadata={
                    "account_name": "Beta",
                    "usage_trend": "flat",
                    "support_ticket_count": 2,
                    "nps_score": 12,
                    "renewal_date": "2099-01-01",
                    "champion_status": "identified",
                    "open_risks": ["procurement slow"],
                },
            ),
            _unit(
                unit_id="risk",
                metadata={
                    "account_name": "Acme",
                    "usage_trend": "declining",
                    "support_ticket_count": 6,
                    "nps_score": -45,
                    "renewal_date": "2000-01-01",
                    "champion_status": "lost",
                    "open_risks": ["exec churn", "low adoption"],
                },
            ),
        ])
    )

    rows = {row["idea_id"]: row for row in report["accounts"]}
    assert rows["healthy"]["status_band"] == "healthy"
    assert rows["watch"]["status_band"] == "watchlist"
    assert rows["risk"]["status_band"] == "at_risk"
    assert rows["healthy"]["health_score"] == 100.0
    assert 50.0 <= rows["watch"]["health_score"] < 75.0
    assert rows["risk"]["health_score"] == 0.0
    assert any("raised score" in driver for driver in rows["healthy"]["drivers"])
    assert any("lowered score" in driver for driver in rows["risk"]["drivers"])
    assert report["summary"]["account_count"] == 3
    assert report["summary"]["at_risk_count"] == 1
    assert report["summary"]["average_health_score"] == round(
        sum(row["health_score"] for row in report["accounts"]) / 3,
        1,
    )


def test_missing_metadata_defaults_to_watchlist_and_identifies_missing_drivers() -> None:
    report = build_account_health_score_export(_store([_unit(unit_id="missing", metadata={})]))

    row = report["accounts"][0]
    assert row["account_name"] == "Account Workspace"
    assert row["health_score"] == 52.0
    assert row["status_band"] == "watchlist"
    assert "missing NPS lowered score" in row["drivers"]
    assert "missing renewal date lowered score" in row["drivers"]
    assert "champion status lowered score" in row["drivers"]


def test_empty_report_is_actionable() -> None:
    report = build_account_health_score_export(_store())
    markdown = render_account_health_score_markdown(report)

    assert report["accounts"] == []
    assert report["summary"] == {
        "account_count": 0,
        "average_health_score": 0.0,
        "at_risk_count": 0,
        "watchlist_count": 0,
        "healthy_count": 0,
    }
    assert "Add customer health metadata" in report["recommendations"][0]
    assert "No account metadata found" in markdown


def test_rows_and_renderers_are_deterministic() -> None:
    report = build_account_health_score_export(
        _store([
            _unit(unit_id="b", metadata={"account_name": "Beta", "usage_trend": "growth", "nps_score": 60, "renewal_date": "2099-01-01", "champion_status": "active"}),
            _unit(unit_id="a", metadata={"account_name": "Acme", "usage_trend": "declining", "support_ticket_count": 8, "nps_score": -30, "renewal_date": "2000-01-01", "champion_status": "lost"}),
        ])
    )

    assert [row["idea_id"] for row in report["accounts"]] == ["a", "b"]
    markdown = render_account_health_score_markdown(report)
    rendered_json = render_account_health_score_json(report)
    assert "## Status Table" in markdown
    assert "## Recommended Next Actions" in markdown
    assert rendered_json == render_account_health_score_json(report)
    parsed = json.loads(rendered_json)
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert list(parsed.keys()) == sorted(parsed.keys())
