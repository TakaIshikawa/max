from __future__ import annotations

from max.spec.ai_red_team_exercise_plan import generate_ai_red_team_exercise_plan


def test_ai_red_team_exercise_plan_orders_scenarios_and_sections() -> None:
    plan = generate_ai_red_team_exercise_plan(
        {
            "scope": ["assistant launch"],
            "safety_boundaries": ["no production customer data"],
            "attack_scenarios": [
                {"scenario": "benign misuse", "severity": "low", "remediation_owner": "product"},
                {"scenario": "credential extraction", "severity": "critical", "remediation_owner": "security"},
            ],
        }
    )

    assert [row["name"] for row in plan["attack_scenarios"]] == ["credential extraction", "benign misuse"]
    assert plan["blockers"] == []
    assert set(plan) >= {"scope", "attack_scenarios", "safety_boundaries", "required_participants", "evidence_capture", "remediation_tracking", "exit_criteria"}


def test_ai_red_team_exercise_plan_blocks_missing_boundary_and_preserves_metadata() -> None:
    source = {"attack_scenarios": [{"scenario": "jailbreak", "severity": "high", "evidence_id": "rt-1", "metadata": {"suite": "policy"}}]}
    plan = generate_ai_red_team_exercise_plan(source)

    assert [row["name"] for row in plan["blockers"]] == ["missing safety boundaries", "missing remediation owner for jailbreak"]
    assert generate_ai_red_team_exercise_plan(source) == plan
    assert plan["attack_scenarios"][0]["metadata"] == {"suite": "policy"}
