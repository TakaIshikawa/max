from __future__ import annotations

from max.spec import generate_environment_promotion_plan, render_environment_promotion_plan_markdown


def test_environment_promotion_plan_defaults_and_flags_blockers() -> None:
    plan = generate_environment_promotion_plan({"approval_gates": [{"environment": "staging", "gate": "security approval", "blocked": True}]})

    assert plan["schema_version"] == "max-environment-promotion-plan/v1"
    assert [row["environment"] for row in plan["promotion_path"]] == ["dev", "staging", "production"]
    assert [row["id"] for row in plan["promotion_path"]] == ["EPP-001", "EPP-002", "EPP-003"]
    assert plan["gate_checks"][0]["status"] == "blocked"
    assert plan["blockers"][0]["gate"] == "security approval"
    assert plan["rollback_checkpoint"]["environment"] == "staging"


def test_environment_promotion_plan_honors_explicit_order_and_markdown() -> None:
    payload = {"environments": [{"environment": "production", "order": 3}, {"environment": "qa", "order": 2}, {"environment": "dev", "order": 1}]}

    first = render_environment_promotion_plan_markdown(payload)
    second = render_environment_promotion_plan_markdown(payload)

    assert first == second
    assert first.index("EPP-001: dev") < first.index("EPP-002: qa") < first.index("EPP-003: production")
    for heading in ["## Promotion Path", "## Gate Checks", "## Blockers", "## Rollback Checkpoint"]:
        assert heading in first
