from __future__ import annotations

from max.spec import generate_profile_rollout_readiness_plan


def test_profile_rollout_readiness_plan_full_inputs_are_ready() -> None:
    plan = generate_profile_rollout_readiness_plan(
        {
            "metadata": {
                "profile_rollout_readiness": {
                    "profile_name": "healthcare",
                    "changed_constraints": ["PHI redaction required"],
                    "source_mix": ["clinical policy", "support signals"],
                    "owners": ["pm", "research"],
                }
            }
        }
    )

    assert plan["summary"]["profile"] == "healthcare"
    assert plan["summary"]["readiness_status"] == "ready"
    assert plan["readiness_gaps"] == []
    assert plan["readiness_checklist"][1]["complete"] is True
    assert plan["dry_run_validation"][0]["name"] == "source_query_replay"
    assert plan["approval_gates"][0]["owner"] == "pm"


def test_profile_rollout_readiness_plan_missing_owner_and_sources_are_gaps() -> None:
    plan = generate_profile_rollout_readiness_plan({"profile_name": "finance"})

    assert plan["summary"]["readiness_status"] == "blocked"
    assert [gap["type"] for gap in plan["readiness_gaps"]] == ["missing_owner", "missing_source_mix"]
    assert plan["risk_register"][0]["severity"] == "high"
    assert plan["approval_gates"][0]["owner"] == "unassigned"
