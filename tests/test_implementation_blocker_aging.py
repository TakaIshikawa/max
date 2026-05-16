from __future__ import annotations

import json

from max.exports.implementation_blocker_aging import (
    export_implementation_blocker_aging,
    render_implementation_blocker_aging_json,
)


def test_implementation_blocker_aging_buckets_escalates_and_sorts() -> None:
    rows = export_implementation_blocker_aging(
        [
            {"account": "Beta", "summary": "SSO config", "age_days": 10, "owner": "CSM"},
            {"account": "Acme", "summary": "Data import", "age_days": 95, "dependency_type": "customer"},
            {"account": "Core", "summary": "API fix", "age_days": 45, "status": "blocked"},
        ]
    )

    assert [row["account"] for row in rows] == ["Acme", "Core", "Beta"]
    assert rows[0]["age_bucket"] == "90_plus"
    assert rows[0]["escalation_status"] == "escalated"
    assert rows[0]["owner"] == "Unassigned"
    assert rows[1]["escalation_status"] == "needs_escalation"


def test_implementation_blocker_aging_defaults_and_json() -> None:
    rows = export_implementation_blocker_aging([{}])

    assert rows[0]["account"] == "Unknown"
    assert rows[0]["age_bucket"] == "0_14"
    assert rows[0]["dependency_type"] == "unknown"
    assert json.loads(render_implementation_blocker_aging_json(rows))
