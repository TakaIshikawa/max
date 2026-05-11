"""Tests for sales pipeline forecast exports."""

from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock

import pytest

from max.exports.sales_pipeline_forecast import (
    KIND,
    SCHEMA_VERSION,
    build_sales_pipeline_forecast,
    render_sales_pipeline_forecast_csv,
    render_sales_pipeline_forecast_json,
    render_sales_pipeline_forecast_markdown,
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


def _mock_store(units: list[MagicMock] | None = None) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    return store


def test_build_schema_and_source_metadata() -> None:
    store = _mock_store([_make_unit()])

    report = build_sales_pipeline_forecast(store, domain="finops")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert "generated_at" in report
    assert report["source"] == {
        "project": "max",
        "entity_type": "sales_pipeline_forecast",
        "domain_filter": "finops",
    }
    assert report["opportunity_count"] == 1
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="finops")


def test_explicit_metadata_extracts_opportunity_fields_and_weighted_value() -> None:
    unit = _make_unit(
        metadata={
            "pipeline_stage": "Contracting",
            "annual_contract_value": "120000",
            "probability": "65",
            "expected_close_month": "2026-08-15",
            "buyer_segment": "enterprise",
            "confidence": "high",
        }
    )

    report = build_sales_pipeline_forecast(_mock_store([unit]))

    opportunity = report["opportunities"][0]
    assert opportunity == {
        "idea_id": "bu-001",
        "title": "Usage-based Billing Copilot",
        "stage": "negotiation",
        "deal_size": 120_000.0,
        "probability": 0.65,
        "expected_close_month": "2026-08",
        "weighted_value": 78_000.0,
        "segment": "enterprise",
        "confidence": "high",
    }


def test_default_estimation_uses_quality_usefulness_and_evidence() -> None:
    unit = _make_unit(
        unit_id="bu-default",
        quality_score=0.9,
        usefulness_score=0.8,
        evidence_signals=["sig-1", "sig-2", "sig-3"],
        metadata={},
    )

    report = build_sales_pipeline_forecast(_mock_store([unit]))

    opportunity = report["opportunities"][0]
    assert opportunity["stage"] == "proposal"
    assert opportunity["deal_size"] == pytest.approx(46_810.0)
    assert opportunity["probability"] == 0.55
    assert opportunity["weighted_value"] == pytest.approx(25_745.5)
    assert opportunity["expected_close_month"][:4].isdigit()
    assert opportunity["segment"] == "finops"
    assert opportunity["confidence"] == "medium"


def test_summary_totals_stage_and_segment_rollups() -> None:
    units = [
        _make_unit(
            unit_id="bu-1",
            title="Enterprise Readiness",
            metadata={
                "sales_stage": "proposal",
                "deal_size": 100_000,
                "probability": 0.5,
                "close_month": "2026-07",
                "segment": "enterprise",
            },
        ),
        _make_unit(
            unit_id="bu-2",
            title="Midmarket Assistant",
            metadata={
                "sales_stage": "qualified",
                "deal_size": 50_000,
                "probability": 0.4,
                "close_month": "2026-07",
                "segment": "midmarket",
            },
        ),
        _make_unit(
            unit_id="bu-3",
            title="Enterprise Audit",
            metadata={
                "sales_stage": "qualified",
                "deal_size": 30_000,
                "probability": 0.3,
                "close_month": "2026-08",
                "segment": "enterprise",
            },
        ),
    ]

    report = build_sales_pipeline_forecast(_mock_store(units))

    summary = report["pipeline_summary"]
    assert summary["opportunity_count"] == 3
    assert summary["total_deal_value"] == 180_000.0
    assert summary["total_weighted_value"] == 79_000.0
    assert summary["average_probability"] == pytest.approx(0.4)
    assert summary["by_stage"] == [
        {
            "stage": "qualified",
            "opportunity_count": 2,
            "total_deal_value": 80_000.0,
            "total_weighted_value": 29_000.0,
            "average_probability": 0.35,
        },
        {
            "stage": "proposal",
            "opportunity_count": 1,
            "total_deal_value": 100_000.0,
            "total_weighted_value": 50_000.0,
            "average_probability": 0.5,
        },
    ]
    assert summary["by_segment"] == [
        {
            "segment": "enterprise",
            "opportunity_count": 2,
            "total_deal_value": 130_000.0,
            "total_weighted_value": 59_000.0,
            "average_probability": 0.4,
        },
        {
            "segment": "midmarket",
            "opportunity_count": 1,
            "total_deal_value": 50_000.0,
            "total_weighted_value": 20_000.0,
            "average_probability": 0.4,
        },
    ]


def test_markdown_json_and_csv_renderers_are_deterministic() -> None:
    report = build_sales_pipeline_forecast(
        _mock_store([
            _make_unit(
                metadata={
                    "sales_stage": "qualified",
                    "deal_size": 40_000,
                    "probability": 0.35,
                    "expected_close_month": "2026-09",
                    "segment": "smb",
                }
            )
        ])
    )

    markdown = render_sales_pipeline_forecast_markdown(report)
    rendered_json = render_sales_pipeline_forecast_json(report)
    rendered_csv = render_sales_pipeline_forecast_csv(report)
    rows = list(csv.DictReader(io.StringIO(rendered_csv)))

    assert "# Sales Pipeline Forecast" in markdown
    assert "## Stage Rollup" in markdown
    assert "Usage-based Billing Copilot" in markdown
    assert markdown.endswith("\n")
    assert rendered_json == render_sales_pipeline_forecast_json(report)
    assert json.loads(rendered_json)["schema_version"] == SCHEMA_VERSION
    assert rendered_csv.splitlines()[0].split(",") == [
        "idea_id",
        "title",
        "stage",
        "deal_size",
        "probability",
        "expected_close_month",
        "weighted_value",
        "segment",
        "confidence",
    ]
    assert rows[0]["idea_id"] == "bu-001"
    assert rows[0]["weighted_value"] == "14000.0"
    assert rendered_csv.endswith("\n")


def test_empty_store_returns_actionable_empty_report() -> None:
    report = build_sales_pipeline_forecast(_mock_store())

    assert report["opportunity_count"] == 0
    assert report["opportunities"] == []
    assert report["pipeline_summary"]["total_deal_value"] == 0
    assert report["pipeline_summary"]["total_weighted_value"] == 0
    assert report["pipeline_summary"]["by_segment"] == []
    assert "No opportunities available" in render_sales_pipeline_forecast_markdown(report)
    assert render_sales_pipeline_forecast_csv(report).startswith("idea_id,title")
