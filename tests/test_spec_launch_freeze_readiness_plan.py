from __future__ import annotations

import json

from max.spec import generate_launch_freeze_readiness_plan


def test_launch_freeze_readiness_plan_uses_hints() -> None:
    plan = generate_launch_freeze_readiness_plan(
        _spec(
            {
                "freeze_window": "Friday 18:00 UTC",
                "freeze_scope": ["api"],
                "allowed_exceptions": ["sev1 fix"],
                "dependency_checkpoints": ["vendor locked"],
                "entry_criteria": ["tests green"],
                "exit_criteria": ["monitoring clean"],
                "communication_channels": ["release room"],
                "validation_checks": ["branch lock"],
            }
        )
    )

    assert plan["freeze_window"]["window"] == "Friday 18:00 UTC"
    assert plan["freeze_scope"][0]["name"] == "api"
    assert plan["validation_checks"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_launch_freeze_readiness_plan_defaults_sparse_input() -> None:
    plan = generate_launch_freeze_readiness_plan({})

    assert plan["freeze_window"]["window"] == "launch freeze window"
    assert plan["freeze_scope"][0]["name"] == "primary workflow"
    assert json.loads(json.dumps(plan)) == plan


def _spec(hints: dict) -> dict:
    return {"metadata": {"launch_freeze_readiness": hints}, "evidence": {"signal_ids": ["sig-1"]}}
