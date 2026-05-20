from __future__ import annotations

from max.spec import generate_feature_entitlement_rollout_plan, render_feature_entitlement_rollout_plan_markdown


def test_feature_entitlement_rollout_plan_detects_readiness_gaps() -> None:
    plan = generate_feature_entitlement_rollout_plan(
        {
            "customer_segments": ["beta", "enterprise"],
            "features": [{"feature": "advanced-export", "entitlement_rules": {"beta": "allow beta cohort"}}],
            "rollout_phases": [{"name": "enterprise", "date": "2026-06-01", "segments": ["enterprise"]}],
        }
    )

    assert plan["schema_version"] == "max-feature-entitlement-rollout-plan/v1"
    assert [row["id"] for row in plan["entitlement_matrix"]] == ["FER-001", "FER-002"]
    assert plan["entitlement_matrix"][1]["rule"] == "entitlement-rule-required"
    assert plan["rollout_phases"][0]["id"] == "FRP-001"
    assert any("missing entitlement rule" in gap["gap"] for gap in plan["readiness_gaps"])
    assert any("missing support owner" in gap["gap"] for gap in plan["readiness_gaps"])
    assert plan["rollback_rules"][0]["condition"] == "rollback-condition-required"


def test_feature_entitlement_rollout_markdown_is_deterministic() -> None:
    payload = {"rollout_phases": [{"name": "second", "date": "2026-07-01"}, {"name": "first", "date": "2026-06-01"}]}

    first = render_feature_entitlement_rollout_plan_markdown(payload)
    second = render_feature_entitlement_rollout_plan_markdown(payload)

    assert first == second
    assert first.index("FRP-001: first") < first.index("FRP-002: second")
    for heading in ["## Entitlement Matrix", "## Rollout Phases", "## Readiness Gaps", "## Rollback Rules"]:
        assert heading in first
