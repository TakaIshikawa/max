from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports import build_procurement_cycle_friction_export
from max.exports.procurement_cycle_friction import (
    render_procurement_cycle_friction_json,
    render_procurement_cycle_friction_markdown,
)


def _unit(unit_id: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = metadata.get("title", unit_id)
    unit.metadata = metadata
    return unit


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store


def test_procurement_cycle_friction_orders_elapsed_severity_and_actions() -> None:
    report = build_procurement_cycle_friction_export(_store([
        _unit("low", {"account": "Acme", "approval_steps": ["legal", "security"], "completed_steps": ["legal"], "elapsed_days": 10}),
        _unit("critical", {"account": "Beta", "approval_steps": ["security", "legal", "finance"], "completed_steps": ["security"], "stalled_artifacts": ["DPA"], "legal_blockers": ["redlines"], "security_blockers": ["pen test"], "elapsed_days": 70}),
    ]))

    assert [row["idea_id"] for row in report["cycle_rows"]] == ["critical", "low"]
    assert report["cycle_rows"][0]["elapsed_time_severity"] == "critical"
    assert report["cycle_rows"][0]["recommended_action"] == "Resolve blocker with accountable stakeholder: redlines."
    assert "finance" in report["cycle_rows"][0]["cycle_stage_summary"]["remaining_steps"]
    assert report["summary"]["blocked_cycle_count"] == 1
    assert report["friction_points"][0]["point"] == "DPA"


def test_procurement_cycle_friction_handles_empty_optional_fields() -> None:
    report = build_procurement_cycle_friction_export(_store([_unit("empty", {})]), domain="sales")
    row = report["cycle_rows"][0]

    assert row["account"] == "Unknown"
    assert row["cycle_stage_summary"]["current_stage"] == "unknown"
    assert row["buyer_roles"] == []
    assert row["elapsed_time_severity"] == "low"
    assert row["recommended_action"] == "Keep buyer roles aligned on the next approval step."
    assert report["source"]["domain_filter"] == "sales"


def test_procurement_cycle_friction_renderers_are_json_serializable() -> None:
    report = build_procurement_cycle_friction_export(_store([]))

    assert json.loads(render_procurement_cycle_friction_json(report))["cycle_rows"] == []
    markdown = render_procurement_cycle_friction_markdown(report)
    assert "Procurement Cycle Friction" in markdown
    assert "No procurement cycle friction metadata" in markdown
