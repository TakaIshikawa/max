from __future__ import annotations

import csv
import json
from io import StringIO
from unittest.mock import MagicMock

from max.analysis.design_brief_operational_dependency_map import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_operational_dependency_map,
    render_design_brief_operational_dependency_map,
    render_design_brief_operational_dependency_map_csv,
)


def test_design_brief_operational_dependency_map_builds_and_renders() -> None:
    store = MagicMock()
    store.get_design_brief.return_value = {
        "id": "dbf-1",
        "title": "Launch Brief",
        "buyer": "COO",
        "workflow_context": "customer onboarding workflow",
        "tech_approach": "FastAPI integrates Slack and Salesforce with Postgres",
        "risks": ["security review pending"],
        "source_idea_ids": ["idea-1"],
    }
    store.get_buildable_unit.return_value = _idea("idea-1")

    report = build_design_brief_operational_dependency_map(store, "dbf-1")
    assert report is not None
    markdown = render_design_brief_operational_dependency_map(report)
    rendered_json = render_design_brief_operational_dependency_map(report, fmt="json")
    rows = list(csv.DictReader(StringIO(render_design_brief_operational_dependency_map_csv(report))))

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.design_brief.operational_dependency_map"
    assert report["design_brief"]["source_idea_ids"] == ["idea-1"]
    assert report["dependency_groups"]
    assert report["owner_handoffs"]
    assert {row["name"] for row in report["external_systems"]} >= {"Slack", "Salesforce", "Postgres"}
    assert report["risk_links"][0]["owner"] == "Security/legal owner"
    assert report["checkpoint_links"]
    assert report["evidence_references"]
    assert markdown.startswith("# Operational Dependency Map: Launch Brief")
    assert json.loads(rendered_json)["source"]["id"] == "dbf-1"
    assert rows[0]["section"] == "dependency_groups"
    assert render_design_brief_operational_dependency_map_csv(report).splitlines()[0] == ",".join(CSV_COLUMNS)


def test_design_brief_operational_dependency_map_missing_brief_returns_none() -> None:
    store = MagicMock()
    store.get_design_brief.return_value = None

    assert build_design_brief_operational_dependency_map(store, "missing") is None


def _idea(idea_id: str) -> MagicMock:
    unit = MagicMock()
    unit.model_dump.return_value = {
        "id": idea_id,
        "tech_approach": "Slack Salesforce integration",
        "domain_risks": ["privacy approval needed"],
    }
    return unit
