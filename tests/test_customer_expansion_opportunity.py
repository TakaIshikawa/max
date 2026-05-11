"""Tests for customer expansion opportunity exports."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.customer_expansion_opportunity import (
    KIND,
    SCHEMA_VERSION,
    build_customer_expansion_opportunity_export,
    render_customer_expansion_opportunity_json,
    render_customer_expansion_opportunity_markdown,
)


def _unit(*, unit_id: str = "idea-1", title: str = "Expansion Workspace", domain: str = "success", metadata: dict | None = None) -> MagicMock:
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

    report = build_customer_expansion_opportunity_export(store, domain="enterprise")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert set(report) == {"schema_version", "kind", "generated_at", "source", "opportunities", "summary", "recommendations"}
    assert report["source"]["domain_filter"] == "enterprise"
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="enterprise")


def test_scores_high_readiness_and_risk_downgraded_accounts() -> None:
    report = build_customer_expansion_opportunity_export(
        _store([
            _unit(unit_id="high", metadata={"account_name": "Zenith", "plan_tier": "Enterprise", "seats_used": 95, "seat_limit": 100, "usage_trend": "growth", "expansion_signals": ["team growth", "budget"], "renewal_date": "2099-01-01", "champion_status": "active", "requested_features": ["sso"]}),
            _unit(unit_id="risk", metadata={"account_name": "Acme", "plan_tier": "pro", "seats_used": 90, "seat_limit": 100, "usage_trend": "growth", "expansion_signals": ["new team"], "renewal_date": "2099-01-01", "champion_status": "active", "open_risks": ["procurement", "support backlog"]}),
        ])
    )

    rows = {row["idea_id"]: row for row in report["opportunities"]}
    assert rows["high"]["readiness_band"] == "high"
    assert rows["risk"]["risk_downgraded"] is True
    assert rows["risk"]["readiness_score"] < rows["high"]["readiness_score"]
    assert any("open risk" in driver for driver in rows["risk"]["drivers"])
    assert report["summary"]["high_readiness_count"] == 1
    assert report["summary"]["risk_downgraded_count"] == 1


def test_empty_report_is_actionable() -> None:
    report = build_customer_expansion_opportunity_export(_store())
    markdown = render_customer_expansion_opportunity_markdown(report)

    assert report["opportunities"] == []
    assert report["summary"]["account_count"] == 0
    assert "Add customer expansion metadata" in report["recommendations"][0]
    assert "No customer expansion metadata found" in markdown


def test_rows_sort_by_readiness_account_and_idea_id_and_renderers_are_stable() -> None:
    report = build_customer_expansion_opportunity_export(
        _store([
            _unit(unit_id="b", metadata={"account_name": "Beta", "seats_used": 90, "seat_limit": 100, "usage_trend": "growth", "expansion_signals": ["budget"], "champion_status": "active", "renewal_date": "2099-01-01"}),
            _unit(unit_id="a", metadata={"account_name": "Acme", "seats_used": 90, "seat_limit": 100, "usage_trend": "growth", "expansion_signals": ["budget"], "champion_status": "active", "renewal_date": "2099-01-01"}),
            _unit(unit_id="c", metadata={"account_name": "Zed", "open_risks": ["blocked"]}),
        ])
    )

    assert [row["idea_id"] for row in report["opportunities"]] == ["a", "b", "c"]
    markdown = render_customer_expansion_opportunity_markdown(report)
    rendered_json = render_customer_expansion_opportunity_json(report)
    assert "## Segment Rollup" in markdown
    assert rendered_json == render_customer_expansion_opportunity_json(report)
    assert json.loads(rendered_json)["schema_version"] == SCHEMA_VERSION
