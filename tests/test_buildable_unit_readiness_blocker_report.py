from __future__ import annotations

import json

from max.exports import build_buildable_unit_readiness_blocker_report
from max.exports.buildable_unit_readiness_blocker_report import render_buildable_unit_readiness_blocker_report_json, render_buildable_unit_readiness_blocker_report_markdown


def test_buildable_unit_readiness_blockers_normalize_and_sort() -> None:
    rows = build_buildable_unit_readiness_blocker_report(
        [
            {"id": "u2", "title": "Ready"},
            {"unit_id": "u1", "issues": ["no stack", "weak-signal"]},
        ]
    )

    assert rows[0]["unit_id"] == "u1"
    assert rows[0]["blocker_categories"] == ["missing_stack", "weak_evidence"]
    assert rows[0]["readiness_status"] == "critical"
    assert rows[1]["readiness_status"] == "ready"


def test_buildable_unit_readiness_blocker_renderers() -> None:
    rows = build_buildable_unit_readiness_blocker_report([{}])

    assert json.loads(render_buildable_unit_readiness_blocker_report_json(rows))[0]["unit_id"] == "unknown-unit"
    assert "| Unit | Title |" in render_buildable_unit_readiness_blocker_report_markdown(rows)
