"""Tests for integration readiness matrix exports."""

from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock

from max.exports import build_integration_readiness_matrix_export as exported_build
from max.exports.integration_readiness_matrix import (
    CSV_COLUMNS,
    KIND,
    SCHEMA_VERSION,
    build_integration_readiness_matrix_export,
    render_integration_readiness_matrix_csv,
    render_integration_readiness_matrix_json,
    render_integration_readiness_matrix_markdown,
)


def test_integration_readiness_matrix_builds_rows_and_summary() -> None:
    store = _store([
        _unit("blocked", "Blocked Slack", "Slack integration", metadata={"integrations": ["Slack"]}),
        _unit(
            "ready",
            "Ready Stripe",
            "Stripe contract tests",
            metadata={"integrations": ["Stripe"], "integration_artifacts": {"Stripe": {"credentials": True, "contract": True, "tests": True, "owner": "payments_owner"}}},
        ),
    ])

    report = build_integration_readiness_matrix_export(store, domain="payments")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["source"]["domain_filter"] == "payments"
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="payments")
    assert [row["readiness"] for row in report["integration_rows"]] == ["blocked", "ready"]
    assert report["integration_rows"][0]["missing_artifacts"] == ["credentials", "contract_assumptions", "test_coverage"]
    assert report["integration_rows"][1]["owner"] == "payments_owner"
    assert report["summary"]["readiness_counts"] == {"blocked": 1, "at_risk": 0, "ready": 1}


def test_integration_readiness_matrix_renderers_and_exports() -> None:
    report = exported_build(_store([_unit("idea", "GitHub Flow", "GitHub integration", metadata={"integrations": ["GitHub"], "integration_artifacts": {"GitHub": {"credentials": True, "contract": True}}})]))
    markdown = render_integration_readiness_matrix_markdown(report)
    csv_text = render_integration_readiness_matrix_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert "# Integration Readiness Matrix" in markdown
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert rows[0]["readiness"] == "at_risk"
    assert "test_coverage" in rows[0]["missing_artifacts"]
    assert json.loads(render_integration_readiness_matrix_json(report))["kind"] == KIND


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store


def _unit(unit_id: str, title: str, tech: str, metadata: dict | None = None) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.tech_approach = tech
    unit.composability_notes = tech
    unit.suggested_stack = {}
    unit.solution = tech
    unit.validation_plan = tech
    unit.evidence_signals = ["sig"]
    unit.inspiring_insights = []
    unit.metadata = metadata or {}
    return unit
