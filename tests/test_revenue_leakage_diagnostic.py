"""Tests for revenue leakage diagnostic exports."""

from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock

from max.exports.revenue_leakage_diagnostic import (
    KIND,
    SCHEMA_VERSION,
    build_revenue_leakage_diagnostic_export,
    render_revenue_leakage_diagnostic_csv,
    render_revenue_leakage_diagnostic_json,
    render_revenue_leakage_diagnostic_markdown,
)


def _unit(unit_id: str, title: str, metadata: dict, *, domain: str = "revenue") -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.domain = domain
    unit.category = "commercial"
    unit.metadata = metadata
    return unit


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store


def test_builds_schema_source_and_category_calculations() -> None:
    store = _store([
        _unit(
            "bu-1",
            "Enterprise Billing",
            {
                "segment": "enterprise",
                "annual_contract_value_usd": 200_000,
                "discount_rate": 0.1,
                "unbilled_usage_usd": 3_500,
                "support_credits_usd": 500,
                "churn_risk_usd": 25_000,
                "payment_failures_usd": 1_000,
                "contract_gap_notes": ["MSA lacks overage clause"],
            },
        )
    ])

    report = build_revenue_leakage_diagnostic_export(store, domain="enterprise")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["source"]["entity_type"] == "revenue_leakage_diagnostic"
    assert report["source"]["domain_filter"] == "enterprise"
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="enterprise")

    row = report["leakage_rows"][0]
    assert row["category_breakdown"] == {
        "discount_leakage": 20_000.0,
        "unbilled_usage": 3_500.0,
        "support_credits": 500.0,
        "churn_risk": 25_000.0,
        "payment_failures": 1_000.0,
        "contract_gaps": 0.0,
    }
    assert row["total_leakage_usd"] == 50_000.0
    assert row["severity"] == "critical"
    assert row["top_category"] == "churn_risk"
    assert report["summary"]["total_leakage_usd"] == 50_000.0
    assert report["summary"]["affected_unit_count"] == 1
    assert report["category_totals"][0]["category"] == "churn_risk"


def test_negative_and_missing_numeric_metadata_is_clamped_to_zero() -> None:
    report = build_revenue_leakage_diagnostic_export(_store([
        _unit(
            "bu-1",
            "No Leakage",
            {
                "annual_contract_value_usd": -100,
                "discount_rate": -0.2,
                "unbilled_usage_usd": -50,
                "support_credits_usd": None,
                "churn_risk_usd": "",
                "payment_failures_usd": "not-a-number",
            },
        )
    ]))

    row = report["leakage_rows"][0]
    assert row["total_leakage_usd"] == 0.0
    assert row["severity"] == "none"
    assert row["leakage_items"] == []
    assert report["summary"]["affected_unit_count"] == 0
    assert report["category_totals"] == []


def test_severity_thresholds_and_deterministic_sorting() -> None:
    report = build_revenue_leakage_diagnostic_export(_store([
        _unit("bu-low", "Low", {"unbilled_usage_usd": 250}),
        _unit("bu-medium", "Medium", {"unbilled_usage_usd": 1_000}),
        _unit("bu-high-b", "High B", {"unbilled_usage_usd": 20_000}),
        _unit("bu-high-a", "High A", {"unbilled_usage_usd": 20_000}),
        _unit("bu-critical", "Critical", {"unbilled_usage_usd": 50_000}),
        _unit("bu-none", "None", {}),
    ]))

    assert [row["idea_id"] for row in report["leakage_rows"]] == [
        "bu-critical",
        "bu-high-a",
        "bu-high-b",
        "bu-medium",
        "bu-low",
        "bu-none",
    ]
    assert [row["severity"] for row in report["leakage_rows"]] == [
        "critical",
        "high",
        "high",
        "medium",
        "low",
        "none",
    ]
    assert report["summary"]["severity_counts"] == {
        "critical": 1,
        "high": 2,
        "medium": 1,
        "low": 1,
        "none": 1,
    }


def test_csv_uses_stable_fields_and_one_row_per_leakage_item() -> None:
    report = build_revenue_leakage_diagnostic_export(_store([
        _unit(
            "bu-1",
            "Billing",
            {
                "arr_usd": 100_000,
                "discount_rate": "5",
                "payment_failures_usd": 2_000,
                "contract_gap_notes": "No auto-renew language",
            },
        )
    ]))

    rows = list(csv.DictReader(io.StringIO(render_revenue_leakage_diagnostic_csv(report))))

    assert rows[0].keys() == {
        "idea_id",
        "title",
        "segment",
        "severity",
        "category",
        "category_label",
        "amount_usd",
        "total_leakage_usd",
        "note",
    }
    assert [row["category"] for row in rows] == ["discount_leakage", "payment_failures", "contract_gaps"]
    assert rows[0]["amount_usd"] == "5000.0"
    assert rows[2]["amount_usd"] == "0.0"
    assert rows[2]["note"] == "No auto-renew language"


def test_empty_store_returns_actionable_empty_report_and_renderers() -> None:
    report = build_revenue_leakage_diagnostic_export(_store([]))

    assert report["leakage_rows"] == []
    assert report["category_totals"] == []
    assert report["summary"]["unit_count"] == 0
    assert report["summary"]["total_leakage_usd"] == 0.0
    assert "No buildable units available" in render_revenue_leakage_diagnostic_markdown(report)
    assert render_revenue_leakage_diagnostic_csv(report).startswith("idea_id,title,segment,severity")


def test_json_markdown_and_csv_outputs_are_parseable_and_deterministic() -> None:
    report = build_revenue_leakage_diagnostic_export(_store([
        _unit("bu-2", "Payment Recovery", {"payment_failures_usd": 2_500}),
        _unit("bu-1", "Usage Capture", {"unbilled_usage_usd": 3_000}),
    ]))

    rendered_json = render_revenue_leakage_diagnostic_json(report)
    rendered_csv = render_revenue_leakage_diagnostic_csv(report)
    markdown = render_revenue_leakage_diagnostic_markdown(report)

    assert json.loads(rendered_json)["schema_version"] == SCHEMA_VERSION
    assert rendered_json == render_revenue_leakage_diagnostic_json(report)
    assert rendered_csv == render_revenue_leakage_diagnostic_csv(report)
    assert list(csv.DictReader(io.StringIO(rendered_csv)))
    assert "## Category Totals" in markdown
    assert "## Recommendations" in markdown
