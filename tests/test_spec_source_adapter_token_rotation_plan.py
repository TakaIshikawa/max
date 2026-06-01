from __future__ import annotations

from max.spec import generate_source_adapter_token_rotation_plan


def test_source_adapter_token_rotation_plan_groups_and_flags_invalid_tokens() -> None:
    plan = generate_source_adapter_token_rotation_plan({"adapters": [{"adapter": "aws", "owner": "team-a", "rotation_window": "night", "expires_at": "2026-01-01T00:00:00Z"}, {"adapter": "cf", "owner": "team-a", "rotation_window": "night", "secret_ref": "sec"}]}, as_of="2026-06-01T00:00:00Z")

    assert plan["schema_version"] == "max.spec.source_adapter_token_rotation_plan.v1"
    assert plan["kind"] == "max.spec.source_adapter_token_rotation_plan"
    assert plan["credential_groups"][0]["adapters"] == ["aws", "cf"]
    assert "expired_token" in plan["validation_issues"]
    assert "missing_token_metadata" in plan["validation_issues"]
    assert plan["rotation_steps"]
    assert plan["validation_fetches"]
