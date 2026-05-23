from __future__ import annotations

import json

from max.spec import generate_session_replay_retention_exception_plan


def test_session_replay_retention_exception_plan_renders_privacy_workflow() -> None:
    plan = generate_session_replay_retention_exception_plan(
        {
            "metadata": {
                "session_replay_retention_exception": {
                    "exceptions": [{"request": "retain checkout replays 45 days", "window": "45 days", "product": "checkout", "account": "enterprise"}],
                    "privacy_controls": ["mask payment fields"],
                    "approval_path": ["privacy counsel"],
                    "purge_criteria": ["purge after defect validation"],
                    "monitoring": ["daily retained replay count"],
                    "rollback": ["restore 14 day retention"],
                }
            },
            "evidence": {"insight_ids": ["sr-1"]},
        }
    )

    assert plan["schema_version"] == "max.spec.session_replay_retention_exception_plan.v1"
    assert plan["exception_scope"][0]["name"] == "retain checkout replays 45 days"
    assert set(plan) >= {"retention_windows", "affected_products_accounts", "privacy_controls", "approval_path", "purge_criteria", "monitoring", "rollback"}
    assert json.loads(json.dumps(plan)) == plan


def test_session_replay_retention_exception_plan_defaults_sparse_input() -> None:
    plan = generate_session_replay_retention_exception_plan({})

    assert plan["exception_scope"][0]["owner"] == "privacy_owner"
    assert plan["purge_criteria"][0]["name"] == "purge retained replays at exception expiry or purpose completion"
