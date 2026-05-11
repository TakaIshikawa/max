"""Tests for API quota utilization exports."""

from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock

from max.exports.api_quota_utilization import (
    KIND,
    SCHEMA_VERSION,
    build_api_quota_utilization_export,
    render_api_quota_utilization_csv,
    render_api_quota_utilization_json,
    render_api_quota_utilization_markdown,
)


def _make_unit(
    *,
    unit_id: str = "bu-001",
    title: str = "Usage API",
    domain: str = "platform",
    metadata: dict | None = None,
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.domain = domain
    unit.metadata = metadata or {}
    return unit


def _mock_store(units: list[MagicMock] | None = None) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    return store


def test_build_schema_source_and_domain_filter() -> None:
    store = _mock_store([_make_unit()])

    report = build_api_quota_utilization_export(store, domain="platform")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert "generated_at" in report
    assert report["source"] == {
        "project": "max",
        "entity_type": "api_quota_utilization",
        "domain_filter": "platform",
    }
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="platform")


def test_quota_rows_compute_under_near_and_over_limit_risk() -> None:
    units = [
        _make_unit(
            unit_id="low",
            title="Internal API",
            metadata={
                "api_calls_monthly": 40_000,
                "quota_limit_monthly": 100_000,
                "quota_cost_per_1k": 2,
                "rate_limit_tier": "standard",
                "owner": "platform",
            },
        ),
        _make_unit(
            unit_id="near",
            title="Partner API",
            metadata={
                "api_calls_monthly": 85_000,
                "quota_limit_monthly": 100_000,
                "quota_cost_per_1k": 4,
                "rate_limit_tier": "growth",
                "owner": "partners",
            },
        ),
        _make_unit(
            unit_id="over",
            title="Events API",
            metadata={
                "api_calls_monthly": 125_000,
                "quota_limit_monthly": 100_000,
                "quota_cost_per_1k": 5,
                "rate_limit_tier": "enterprise",
                "owner": "platform",
            },
        ),
    ]

    report = build_api_quota_utilization_export(_mock_store(units))
    rows_by_id = {row["idea_id"]: row for row in report["quota_rows"]}

    assert rows_by_id["low"]["utilization_pct"] == 40.0
    assert rows_by_id["low"]["projected_overage"] == 0
    assert rows_by_id["low"]["estimated_overage_cost"] == 0
    assert rows_by_id["low"]["risk_level"] == "low"
    assert rows_by_id["near"]["utilization_pct"] == 85.0
    assert rows_by_id["near"]["risk_level"] == "medium"
    assert rows_by_id["over"]["utilization_pct"] == 125.0
    assert rows_by_id["over"]["projected_overage"] == 25_000
    assert rows_by_id["over"]["estimated_overage_cost"] == 125.0
    assert rows_by_id["over"]["risk_level"] == "high"


def test_summary_aggregates_by_owner_and_domain() -> None:
    report = build_api_quota_utilization_export(
        _mock_store([
            _make_unit(
                unit_id="a",
                domain="platform",
                metadata={"api_calls_monthly": 110_000, "quota_limit_monthly": 100_000, "quota_cost_per_1k": 3, "owner": "alice"},
            ),
            _make_unit(
                unit_id="b",
                domain="growth",
                metadata={"api_calls_monthly": 50_000, "quota_limit_monthly": 100_000, "quota_cost_per_1k": 3, "owner": "alice"},
            ),
        ])
    )

    summary = report["summary"]
    assert summary["total_api_calls_monthly"] == 160_000
    assert summary["total_quota_limit_monthly"] == 200_000
    assert summary["total_projected_overage"] == 10_000
    assert summary["total_estimated_overage_cost"] == 30.0
    assert summary["risk_counts"] == {"low": 1, "medium": 0, "high": 1}
    assert summary["by_owner"] == [
        {
            "owner": "alice",
            "unit_count": 2,
            "api_calls_monthly": 160_000,
            "quota_limit_monthly": 200_000,
            "projected_overage": 10_000,
            "estimated_overage_cost": 30.0,
            "highest_risk_level": "high",
        }
    ]
    assert [row["domain"] for row in summary["by_domain"]] == ["growth", "platform"]


def test_nested_quota_metadata_and_defaults() -> None:
    report = build_api_quota_utilization_export(
        _mock_store([
            _make_unit(
                metadata={
                    "api_quota": {
                        "monthly_api_calls": "95000",
                        "monthly_quota_limit": "100000",
                        "overage_cost_per_1k": "2.5",
                        "api_tier": "pro",
                        "quota_owner": "ops",
                    }
                }
            )
        ])
    )

    row = report["quota_rows"][0]
    assert row["owner"] == "ops"
    assert row["rate_limit_tier"] == "pro"
    assert row["utilization_pct"] == 95.0
    assert row["risk_level"] == "high"


def test_markdown_json_and_csv_renderers_are_stable() -> None:
    report = build_api_quota_utilization_export(
        _mock_store([
            _make_unit(
                metadata={
                    "api_calls_monthly": 125_000,
                    "quota_limit_monthly": 100_000,
                    "quota_cost_per_1k": 5,
                    "owner": "platform",
                }
            )
        ])
    )

    markdown = render_api_quota_utilization_markdown(report)
    rendered_json = render_api_quota_utilization_json(report)
    rendered_csv = render_api_quota_utilization_csv(report)
    rows = list(csv.DictReader(io.StringIO(rendered_csv)))

    assert "# API Quota Utilization" in markdown
    assert "## Owner Rollup" in markdown
    assert "Usage API" in markdown
    assert markdown.endswith("\n")
    assert rendered_json == render_api_quota_utilization_json(report)
    assert json.loads(rendered_json)["schema_version"] == SCHEMA_VERSION
    assert rows == [
        {
            "idea_id": "bu-001",
            "title": "Usage API",
            "domain": "platform",
            "owner": "platform",
            "rate_limit_tier": "standard",
            "api_calls_monthly": "125000.0",
            "quota_limit_monthly": "100000.0",
            "utilization_pct": "125.0",
            "projected_overage": "25000.0",
            "quota_cost_per_1k": "5.0",
            "estimated_overage_cost": "125.0",
            "risk_level": "high",
        }
    ]
