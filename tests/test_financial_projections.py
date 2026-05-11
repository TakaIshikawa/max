"""Tests for buildable-unit financial projections export."""

from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock

import pytest

from max.exports.financial_projections import (
    KIND,
    SCHEMA_VERSION,
    _calculate_roi,
    _estimate_costs,
    build_financial_projections,
    render_financial_projections_csv,
    render_financial_projections_json,
    render_financial_projections_markdown,
)


def _make_unit(
    *,
    unit_id: str = "bu-001",
    title: str = "Usage-based Billing Copilot",
    domain: str = "finops",
    category: str = "application",
    quality_score: float = 0.7,
    usefulness_score: float = 0.6,
    evidence_signals: list[str] | None = None,
    metadata: dict | None = None,
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.domain = domain
    unit.category = category
    unit.quality_score = quality_score
    unit.usefulness_score = usefulness_score
    unit.evidence_signals = evidence_signals or ["sig-1", "sig-2"]
    unit.metadata = metadata or {}
    return unit


def _mock_store(units: list | None = None) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    return store


def test_build_schema() -> None:
    store = _mock_store([_make_unit()])

    report = build_financial_projections(store, domain="finops")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert "generated_at" in report
    assert report["source"]["entity_type"] == "financial_projections"
    assert report["source"]["domain_filter"] == "finops"
    assert report["projection_count"] == 1
    assert len(report["projections"]) == 1
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="finops")


def test_projection_fields() -> None:
    unit = _make_unit(
        metadata={
            "development_cost": 80_000,
            "infrastructure_cost": 2_000,
            "maintenance_cost": 3_000,
            "projected_monthly_revenue": 22_000,
            "confidence": "high",
        }
    )
    report = build_financial_projections(_mock_store([unit]))

    projection = report["projections"][0]
    assert projection == {
        "idea_id": "bu-001",
        "title": "Usage-based Billing Copilot",
        "estimated_dev_cost": 80_000.0,
        "estimated_monthly_cost": 5_000.0,
        "projected_monthly_revenue": 22_000.0,
        "payback_months": pytest.approx(4.71),
        "roi_12_month": pytest.approx(0.8857),
        "confidence": "high",
    }


def test_estimate_costs_defaults() -> None:
    costs = _estimate_costs(_make_unit(metadata={}))

    assert costs == {
        "development_cost": 50_000.0,
        "infrastructure_cost": 1_000.0,
        "maintenance_cost": 2_500.0,
        "monthly_cost": 3_500.0,
    }


def test_estimate_costs_nested_financials() -> None:
    costs = _estimate_costs(
        _make_unit(
            metadata={
                "financials": {
                    "dev_cost": "120000",
                    "infra_cost": "4500",
                    "support_cost": "5500",
                }
            }
        )
    )

    assert costs["development_cost"] == 120_000.0
    assert costs["monthly_cost"] == 10_000.0


def test_calculate_roi() -> None:
    roi = _calculate_roi(
        {"development_cost": 80_000.0, "monthly_cost": 5_000.0},
        revenue=25_000.0,
    )

    assert roi["payback_months"] == pytest.approx(4.0)
    assert roi["net_profit"] == pytest.approx(160_000.0)
    assert roi["roi_12_month"] == pytest.approx(1.1429)


def test_calculate_roi_no_payback() -> None:
    roi = _calculate_roi(
        {"development_cost": 80_000.0, "monthly_cost": 10_000.0},
        revenue=5_000.0,
    )

    assert roi["payback_months"] is None
    assert roi["roi_12_month"] < 0


def test_render_markdown() -> None:
    report = build_financial_projections(
        _mock_store([
            _make_unit(
                metadata={
                    "development_cost": 80_000,
                    "monthly_revenue": 25_000,
                }
            )
        ])
    )

    markdown = render_financial_projections_markdown(report)

    assert "# Financial Projections" in markdown
    assert "## Summary" in markdown
    assert "## Per-Idea Details" in markdown
    assert "## Portfolio Totals" in markdown
    assert "| Metric | Value |" in markdown
    assert "Usage-based Billing Copilot" in markdown
    assert markdown.endswith("\n")


def test_render_json() -> None:
    report = build_financial_projections(_mock_store([_make_unit()]))

    rendered = render_financial_projections_json(report)
    parsed = json.loads(rendered)

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["projection_count"] == 1
    assert parsed["projections"][0]["idea_id"] == "bu-001"


def test_render_csv() -> None:
    report = build_financial_projections(_mock_store([_make_unit()]))

    rendered = render_financial_projections_csv(report)
    rows = list(csv.DictReader(io.StringIO(rendered)))

    assert rendered.splitlines()[0].split(",") == [
        "idea_id",
        "title",
        "estimated_dev_cost",
        "estimated_monthly_cost",
        "projected_monthly_revenue",
        "payback_months",
        "roi_12_month",
        "confidence",
    ]
    assert rows[0]["idea_id"] == "bu-001"


def test_empty_store_produces_valid_output() -> None:
    report = build_financial_projections(_mock_store())

    assert report["projection_count"] == 0
    assert report["projections"] == []
    assert report["portfolio_summary"]["total_dev_cost"] == 0
    assert report["portfolio_summary"]["average_roi_12_month"] == 0.0
    assert render_financial_projections_csv(report).startswith("idea_id,title")


def test_multiple_units_aggregation() -> None:
    units = [
        _make_unit(
            unit_id="bu-1",
            domain="finops",
            metadata={
                "development_cost": 50_000,
                "infrastructure_cost": 1_000,
                "maintenance_cost": 2_000,
                "monthly_revenue": 15_000,
            },
        ),
        _make_unit(
            unit_id="bu-2",
            title="Security Evidence Pack",
            domain="security",
            metadata={
                "development_cost": 100_000,
                "infrastructure_cost": 2_000,
                "maintenance_cost": 3_000,
                "monthly_revenue": 30_000,
            },
        ),
    ]

    report = build_financial_projections(_mock_store(units))

    summary = report["portfolio_summary"]
    assert report["projection_count"] == 2
    assert summary["total_dev_cost"] == 150_000.0
    assert summary["total_monthly_cost"] == 8_000.0
    assert summary["total_monthly_revenue"] == 45_000.0
    assert {segment["segment"] for segment in summary["by_segment"]} == {
        "finops",
        "security",
    }
