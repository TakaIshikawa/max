"""Tests for pricing sensitivity exports."""

from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock

import pytest

from max.exports.pricing_sensitivity import (
    KIND,
    SCHEMA_VERSION,
    build_pricing_sensitivity_report,
    render_pricing_sensitivity_csv,
    render_pricing_sensitivity_json,
    render_pricing_sensitivity_markdown,
)


def _make_unit(
    *,
    unit_id: str = "bu-001",
    title: str = "Usage Pricing Console",
    domain: str = "finops",
    category: str = "application",
    quality_score: float = 0.7,
    evidence_signals: list[str] | None = None,
    metadata: dict | None = None,
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.domain = domain
    unit.category = category
    unit.quality_score = quality_score
    unit.evidence_signals = evidence_signals or ["sig-1", "sig-2"]
    unit.metadata = metadata or {}
    return unit


def _mock_store(units: list[MagicMock] | None = None) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    return store


def test_build_schema_source_and_domain_filter() -> None:
    store = _mock_store([_make_unit()])

    report = build_pricing_sensitivity_report(store, domain="finops")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert "generated_at" in report
    assert report["source"]["entity_type"] == "pricing_sensitivity"
    assert report["source"]["domain_filter"] == "finops"
    assert report["source"]["defaults"]["base_price"] == 49.0
    assert report["scenario_count"] == 3
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="finops")


def test_baseline_downside_and_upside_calculations() -> None:
    unit = _make_unit(
        metadata={
            "base_price": 100,
            "target_users": 1_000,
            "conversion_rate": 0.1,
            "churn_rate": 0.05,
            "expansion_rate": 0.1,
            "segment": "enterprise",
            "confidence": "high",
        }
    )

    report = build_pricing_sensitivity_report(_mock_store([unit]))

    baseline, downside, upside = report["scenarios"]
    assert baseline["scenario"] == "baseline"
    assert baseline["base_price"] == 100.0
    assert baseline["converted_users"] == 100.0
    assert baseline["retained_users"] == 95.0
    assert baseline["monthly_revenue"] == 10_450.0
    assert baseline["annual_revenue"] == 125_400.0
    assert baseline["confidence"] == "high"

    assert downside["scenario"] == "downside"
    assert downside["base_price"] == 90.0
    assert downside["conversion_rate"] == 0.075
    assert downside["churn_rate"] == 0.0675
    assert downside["expansion_rate"] == 0.05
    assert downside["monthly_revenue"] == pytest.approx(6_609.09)

    assert upside["scenario"] == "upside"
    assert upside["base_price"] == 110.0
    assert upside["conversion_rate"] == 0.125
    assert upside["churn_rate"] == 0.0375
    assert upside["expansion_rate"] == 0.15
    assert upside["monthly_revenue"] == pytest.approx(15_219.53)


def test_missing_metadata_uses_documented_defaults() -> None:
    report = build_pricing_sensitivity_report(_mock_store([_make_unit(metadata={})]))

    baseline = report["scenarios"][0]
    assert baseline["base_price"] == 49.0
    assert baseline["target_users"] == 1_000.0
    assert baseline["conversion_rate"] == 0.05
    assert baseline["churn_rate"] == 0.03
    assert baseline["expansion_rate"] == 0.02
    assert baseline["monthly_revenue"] == pytest.approx(2_424.03)
    assert baseline["confidence"] == "low"


def test_nested_metadata_and_percentage_rates_are_supported() -> None:
    unit = _make_unit(
        metadata={
            "pricing": {
                "base_price": "80",
                "target_users": "500",
                "conversion_rate": "12",
                "churn_rate": "4",
                "expansion_rate": "5",
                "confidence": "low",
            },
            "market_segment": "midmarket",
        }
    )

    report = build_pricing_sensitivity_report(_mock_store([unit]))

    baseline = report["scenarios"][0]
    assert baseline["base_price"] == 80.0
    assert baseline["target_users"] == 500.0
    assert baseline["conversion_rate"] == 0.12
    assert baseline["churn_rate"] == 0.04
    assert baseline["expansion_rate"] == 0.05
    assert baseline["monthly_revenue"] == 4_838.4
    assert baseline["confidence"] == "low"
    assert baseline["segment"] == "midmarket"


def test_portfolio_summary_totals_and_segment_aggregation() -> None:
    units = [
        _make_unit(
            unit_id="bu-1",
            domain="finops",
            metadata={
                "base_price": 100,
                "target_users": 1_000,
                "conversion_rate": 0.1,
                "churn_rate": 0.05,
                "expansion_rate": 0.1,
                "segment": "enterprise",
            },
        ),
        _make_unit(
            unit_id="bu-2",
            domain="growth",
            metadata={
                "base_price": 50,
                "target_users": 500,
                "conversion_rate": 0.2,
                "churn_rate": 0.1,
                "expansion_rate": 0,
                "segment": "smb",
            },
        ),
    ]

    report = build_pricing_sensitivity_report(_mock_store(units))
    summary = report["portfolio_summary"]

    assert summary["unit_count"] == 2
    assert summary["baseline_monthly_revenue"] == 14_950.0
    assert summary["scenario_totals"][0] == {
        "scenario": "baseline",
        "unit_count": 2,
        "converted_users": 200.0,
        "retained_users": 185.0,
        "monthly_revenue": 14_950.0,
        "annual_revenue": 179_400.0,
    }
    assert summary["by_segment"][0]["segment"] == "enterprise"
    assert summary["by_segment"][0]["scenario"] == "baseline"
    assert summary["by_segment"][3]["segment"] == "smb"
    assert summary["by_segment"][3]["scenario"] == "baseline"


def test_empty_store_returns_empty_report_and_renderers() -> None:
    report = build_pricing_sensitivity_report(_mock_store())

    assert report["scenario_count"] == 0
    assert report["scenarios"] == []
    assert report["portfolio_summary"]["unit_count"] == 0
    assert report["portfolio_summary"]["scenario_totals"] == []
    assert "No buildable units available" in render_pricing_sensitivity_markdown(report)
    assert render_pricing_sensitivity_csv(report).startswith("idea_id,title,segment")


def test_markdown_json_and_csv_renderers_are_deterministic() -> None:
    report = build_pricing_sensitivity_report(
        _mock_store([
            _make_unit(
                metadata={
                    "base_price": 120,
                    "target_users": 250,
                    "conversion_rate": 0.08,
                    "churn_rate": 0.04,
                    "expansion_rate": 0.02,
                    "segment": "enterprise",
                }
            )
        ])
    )

    markdown = render_pricing_sensitivity_markdown(report)
    rendered_json = render_pricing_sensitivity_json(report)
    rendered_csv = render_pricing_sensitivity_csv(report)
    rows = list(csv.DictReader(io.StringIO(rendered_csv)))

    assert "# Pricing Sensitivity" in markdown
    assert "## Segment Rollup" in markdown
    assert "Usage Pricing Console" in markdown
    assert markdown.endswith("\n")
    assert rendered_json == render_pricing_sensitivity_json(report)
    assert json.loads(rendered_json)["schema_version"] == SCHEMA_VERSION
    assert rendered_csv.splitlines()[0].split(",") == [
        "idea_id",
        "title",
        "segment",
        "scenario",
        "base_price",
        "target_users",
        "conversion_rate",
        "converted_users",
        "churn_rate",
        "retained_users",
        "expansion_rate",
        "monthly_revenue",
        "annual_revenue",
        "confidence",
    ]
    assert [row["scenario"] for row in rows] == ["baseline", "downside", "upside"]
    assert rows[0]["monthly_revenue"] == "2350.08"
    assert rendered_csv.endswith("\n")
