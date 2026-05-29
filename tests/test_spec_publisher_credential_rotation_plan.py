from __future__ import annotations

from max.spec import generate_publisher_credential_rotation_plan


def test_publisher_credential_rotation_plan_redacts_secrets_and_handles_modes() -> None:
    plan = generate_publisher_credential_rotation_plan({"metadata": {"publisher_credential_rotation": {"credential_inventory": [{"label": "prod-key", "secret": "do-not-echo", "mode": "live"}, {"label": "dry-key", "token": "hide", "mode": "dry-run"}]}}})
    text = str(plan)
    assert "do-not-echo" not in text
    assert "hide" not in text
    assert [row["name"] for row in plan["credential_inventory"]] == ["dry-key", "prod-key"]
    assert plan["validation_checks"]


def test_publisher_credential_rotation_plan_sparse_defaults() -> None:
    plan = generate_publisher_credential_rotation_plan({})
    assert plan["affected_publishers"]
    assert plan["audit_evidence"]
