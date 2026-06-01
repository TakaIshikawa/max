from __future__ import annotations

from max.spec.source_adapter_credential_expiry_plan import generate_source_adapter_credential_expiry_plan


def test_credential_expiry_plan_prioritizes_high_risk_near_expiry() -> None:
    plan = generate_source_adapter_credential_expiry_plan(
        [
            {"id": "later", "adapter": "rss", "expires_at": "2026-07-15T00:00:00Z"},
            {"id": "soon", "adapter": "github", "expires_at": "2026-06-05T00:00:00Z"},
        ],
        as_of="2026-06-01T00:00:00Z",
    )

    assert [row["id"] for row in plan["affected_adapters"]] == ["soon", "later"]
    assert plan["affected_adapters"][0]["severity"] == "high"


def test_credential_expiry_plan_renders_adapter_owner_and_action() -> None:
    plan = generate_source_adapter_credential_expiry_plan(
        [{"id": "c1", "adapter": "openrouter_models", "owner": "ml-platform", "expires_at": "2026-06-03T00:00:00Z"}],
        as_of="2026-06-01T00:00:00Z",
    )

    action = plan["rotation_actions"][0]
    assert action["adapter"] == "openrouter_models"
    assert action["owner"] == "ml-platform"
    assert "Rotate credential" in action["action"]


def test_credential_expiry_plan_empty_input_has_no_action_plan() -> None:
    plan = generate_source_adapter_credential_expiry_plan([], as_of="2026-06-01T00:00:00Z")

    assert plan["affected_adapters"] == []
    assert plan["rotation_actions"][0]["type"] == "no_action"
