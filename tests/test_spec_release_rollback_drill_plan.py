from __future__ import annotations

import json

from max.spec.release_rollback_drill_plan import (
    SCHEMA_VERSION,
    generate_release_rollback_drill_plan,
    render_release_rollback_drill_plan_markdown,
)


def _spec() -> dict:
    return {
        "title": "Checkout Release 2026.05 Rollback Drill",
        "release_components": [
            {"component": "checkout-api", "release": "2026.05", "rollback_method": "redeploy previous image", "owner": "Payments"},
            {"component": "pricing-worker", "release": "2026.05", "rollback_method": "disable worker flag", "owner": "Pricing"},
        ],
        "rollback_triggers": [
            {"trigger": "p95 latency degraded", "threshold": "latency exceeds baseline by 40%", "owner": "SRE"},
            {"trigger": "payment failures", "threshold": "5xx payment failure rate above 1%", "owner": "Incident Lead"},
            {"trigger": "documentation typo", "threshold": "release note correction requested"},
        ],
        "drill_participants": [
            {"name": "Mina", "role": "incident_commander", "contact": "#incidents"},
            {"name": "Omar", "role": "sre", "contact": "#ops"},
            {"name": "Tara", "role": "communications", "contact": "#comms"},
            {"name": "Lee", "role": "observer"},
        ],
        "validation_probes": [
            {"probe": "synthetic checkout", "target": "checkout-api", "expected_result": "200 response", "owner": "QA"},
            {"probe": "worker queue drain", "target": "pricing-worker", "required": False},
        ],
        "timing_targets": [
            {"name": "complete rollback", "target_minutes": 12, "owner": "Release"},
            {"name": "detect trigger", "target_minutes": 4, "owner": "SRE"},
        ],
        "communication_checkpoints": [
            {"checkpoint": "rollback decision", "channel": "#incidents", "timing": "T+5", "owner": "Tara"},
            {"checkpoint": "drill start", "channel": "#release", "timing": "T+0", "owner": "Mina"},
        ],
    }


def test_release_rollback_drill_returns_structured_output() -> None:
    first = generate_release_rollback_drill_plan(_spec())
    second = generate_release_rollback_drill_plan(_spec())

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == "max.release_rollback_drill_plan"
    assert json.loads(json.dumps(first))["summary"]["title"] == "Checkout Release 2026.05 Rollback Drill"
    assert [row["component"] for row in first["drill_scope"]] == ["checkout-api", "pricing-worker"]
    assert len(first["trigger_matrix"]) == 3
    assert len(first["validation_probes"]) == 2
    assert first["timing_targets"][0]["name"] == "detect trigger"
    assert first["follow_up_actions"][0]["action"] == "Document rollback decision gaps and update trigger thresholds."


def test_release_rollback_drill_classifies_triggers() -> None:
    plan = generate_release_rollback_drill_plan(_spec())

    assert [(row["trigger"], row["classification"]) for row in plan["trigger_matrix"]] == [
        ("payment failures", "critical"),
        ("p95 latency degraded", "warning"),
        ("documentation typo", "informational"),
    ]
    assert plan["trigger_matrix"][0]["decision"].startswith("rollback immediately")
    assert plan["summary"]["critical_trigger_count"] == 1


def test_release_rollback_drill_groups_participants() -> None:
    plan = generate_release_rollback_drill_plan(_spec())

    assert [(row["name"], row["group"]) for row in plan["participant_roles"]] == [
        ("Mina", "command"),
        ("Tara", "communications"),
        ("Omar", "execution"),
        ("Lee", "observer"),
    ]


def test_release_rollback_drill_markdown_is_deterministic() -> None:
    plan = generate_release_rollback_drill_plan(_spec())

    first = render_release_rollback_drill_plan_markdown(plan)
    second = render_release_rollback_drill_plan_markdown(plan)

    assert first == second
    assert first.startswith("# Checkout Release 2026.05 Rollback Drill Release Rollback Drill Plan")
    assert "## Drill Agenda" in first
    assert "### SCP1: checkout-api" in first
    assert "## Rollback Decision Points" in first
    assert "### TRG1: payment failures" in first
    assert "## Validation Checklist" in first
    assert "synthetic checkout" in first
    assert "## Retrospective" in first
    assert "Document rollback decision gaps" in first
