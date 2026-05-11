"""Tests for implementation risk heatmap exports."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.implementation_risk_heatmap import (
    KIND,
    SCHEMA_VERSION,
    build_implementation_risk_heatmap_export,
    render_implementation_risk_heatmap_json,
    render_implementation_risk_heatmap_markdown,
)


def _unit(
    unit_id: str = "idea-1",
    title: str = "Implementation Plan",
    metadata: dict | None = None,
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.metadata = metadata or {}
    return unit


def _store(units: list[MagicMock] | None = None) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    return store


def test_builds_schema_source_and_domain_filter() -> None:
    store = _store([_unit(metadata={"engineering_effort": "low"})])

    report = build_implementation_risk_heatmap_export(store, domain="platform")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert "generated_at" in report
    assert report["source"]["entity_type"] == "implementation_risk_heatmap"
    assert report["source"]["domain_filter"] == "platform"
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="platform")


def test_scores_high_medium_and_low_risk_rows_deterministically() -> None:
    report = build_implementation_risk_heatmap_export(
        _store([
            _unit(
                "low",
                "Low Risk",
                {
                    "engineering_effort": "low",
                    "dependency_count": 0,
                    "unknowns": [],
                    "security_complexity": "low",
                    "data_migration_required": False,
                    "team_readiness": "ready",
                    "deadline_pressure": "low",
                },
            ),
            _unit(
                "high",
                "High Risk",
                {
                    "engineering_effort": "critical",
                    "dependency_count": 8,
                    "unknowns": ["legacy schema", "vendor API", "rollback"],
                    "security_complexity": "high",
                    "data_migration_required": True,
                    "team_readiness": "low",
                    "deadline_pressure": "high",
                },
            ),
            _unit(
                "medium",
                "Medium Risk",
                {
                    "engineering_effort": "medium",
                    "dependency_count": 3,
                    "unknowns": "unclear rollout, acceptance criteria",
                    "security_complexity": "medium",
                    "data_migration_required": "no",
                    "team_readiness": 60,
                    "deadline_pressure": "medium",
                },
            ),
        ])
    )

    assert [row["idea_id"] for row in report["risk_rows"]] == ["high", "medium", "low"]
    rows = {row["idea_id"]: row for row in report["risk_rows"]}
    assert rows["high"]["severity"] == "high"
    assert rows["medium"]["severity"] == "medium"
    assert rows["low"]["severity"] == "low"
    assert rows["high"]["total_risk_score"] == 82.1
    assert rows["medium"]["total_risk_score"] == 41.4
    assert rows["low"]["total_risk_score"] == 10.7
    assert rows["high"]["risk_drivers"] == [
        "Dependency count",
        "Engineering effort",
        "Data migration required",
    ]
    assert report["summary"]["severity_counts"] == {"high": 1, "medium": 1, "low": 1}
    assert report["summary"]["top_risk_drivers"][0] == {"driver": "Data migration required", "count": 1}


def test_normalizes_boolean_numeric_string_and_nested_metadata_values() -> None:
    report = build_implementation_risk_heatmap_export(
        _store([
            _unit(
                metadata={
                    "implementation": {
                        "engineering_effort": "120",
                        "dependency_count": ["auth", "billing"],
                        "unknowns": True,
                        "security_complexity": False,
                        "data_migration_required": "required",
                        "team_readiness": False,
                        "deadline_pressure": 101,
                    }
                }
            )
        ])
    )

    scores = report["risk_rows"][0]["dimension_scores"]
    assert scores == {
        "engineering_effort": 100.0,
        "dependency_count": 30.0,
        "unknowns": 70.0,
        "security_complexity": 10.0,
        "data_migration_required": 80.0,
        "team_readiness": 90.0,
        "deadline_pressure": 100.0,
    }
    assert report["risk_rows"][0]["total_risk_score"] == 68.6
    assert report["risk_rows"][0]["severity"] == "medium"


def test_missing_metadata_is_bounded_and_low_risk() -> None:
    report = build_implementation_risk_heatmap_export(_store([_unit(metadata={})]))

    row = report["risk_rows"][0]
    assert row["dimension_scores"] == {
        "engineering_effort": 0.0,
        "dependency_count": 0.0,
        "unknowns": 0.0,
        "security_complexity": 0.0,
        "data_migration_required": 0.0,
        "team_readiness": 0.0,
        "deadline_pressure": 0.0,
    }
    assert row["total_risk_score"] == 0.0
    assert row["severity"] == "low"
    assert row["risk_drivers"] == []


def test_empty_store_returns_actionable_report() -> None:
    report = build_implementation_risk_heatmap_export(_store())
    markdown = render_implementation_risk_heatmap_markdown(report)
    rendered_json = render_implementation_risk_heatmap_json(report)

    assert report["risk_rows"] == []
    assert report["summary"]["idea_count"] == 0
    assert report["summary"]["average_risk_score"] == 0.0
    assert report["summary"]["severity_counts"] == {"high": 0, "medium": 0, "low": 0}
    assert "Add implementation risk metadata" in report["recommendations"][0]
    assert "No buildable units found" in markdown
    assert json.loads(rendered_json)["risk_rows"] == []


def test_markdown_and_json_are_deterministic_and_parseable() -> None:
    report = build_implementation_risk_heatmap_export(
        _store([
            _unit(
                "b",
                "Beta Importer",
                {
                    "engineering_effort": "high",
                    "dependency_count": 4,
                    "unknowns": ["mapping"],
                    "security_complexity": "medium",
                    "data_migration_required": True,
                    "team_readiness": "medium",
                    "deadline_pressure": "high",
                },
            )
        ])
    )

    markdown = render_implementation_risk_heatmap_markdown(report)
    rendered_json = render_implementation_risk_heatmap_json(report)

    assert markdown == render_implementation_risk_heatmap_markdown(report)
    assert rendered_json == render_implementation_risk_heatmap_json(report)
    assert "# Implementation Risk Heatmap" in markdown
    assert "## Heatmap" in markdown
    assert "Beta Importer" in markdown
    assert markdown.endswith("\n")
    parsed = json.loads(rendered_json)
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert list(parsed.keys()) == sorted(parsed.keys())
