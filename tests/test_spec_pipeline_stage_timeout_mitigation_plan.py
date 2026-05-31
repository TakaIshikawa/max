from __future__ import annotations

from max.spec.pipeline_stage_timeout_mitigation_plan import generate_pipeline_stage_timeout_mitigation_plan


def test_pipeline_stage_timeout_mitigation_plan_handles_single_stage_timeout() -> None:
    plan = generate_pipeline_stage_timeout_mitigation_plan(
        {
            "metadata": {
                "pipeline_stage_timeout_mitigation": {
                    "stages": [
                        {
                            "id": "extract",
                            "stage": "Extract",
                            "owner": "ingestion",
                            "timeout_count": 1,
                            "runtime_seconds": 95,
                            "budget_seconds": 60,
                        }
                    ]
                }
            }
        }
    )

    assert plan["summary"]["affected_stage_count"] == 1
    assert plan["affected_stages"][0]["severity"] == "high"
    assert plan["root_cause_hypotheses"][0]["stage_id"] == "extract"
    assert plan["immediate_actions"][0]["owner"] == "ingestion"
    assert plan["validation_checks"][0]["name"] == "timeout_budget_compliance"
    assert plan["rollback_triggers"][0]["name"] == "timeout_rate_worsens"


def test_pipeline_stage_timeout_mitigation_plan_handles_multi_stage_timeouts() -> None:
    plan = generate_pipeline_stage_timeout_mitigation_plan(
        {
            "timeouts": [
                {"id": "load", "name": "Load", "timeout_count": 5, "runtime_seconds": 120, "budget_seconds": 80},
                {"id": "transform", "name": "Transform", "timeout": True, "runtime_seconds": 45, "budget_seconds": 60},
            ]
        }
    )

    assert [stage["id"] for stage in plan["affected_stages"]] == ["load", "transform"]
    assert plan["summary"]["highest_severity"] == "critical"
    assert len(plan["root_cause_hypotheses"]) == 2
    assert len(plan["immediate_actions"]) == 2
    assert [owner["owner"] for owner in plan["owners"]] == ["pipeline_lead", "stage_owner"]


def test_pipeline_stage_timeout_mitigation_plan_no_timeout_returns_monitoring_plan() -> None:
    plan = generate_pipeline_stage_timeout_mitigation_plan(
        {
            "stages": [
                {"id": "extract", "stage": "Extract", "runtime_seconds": 20, "budget_seconds": 60},
                {"id": "load", "stage": "Load", "runtime_seconds": 30, "budget_seconds": 60},
            ]
        }
    )

    assert plan["summary"]["risk_level"] == "low"
    assert plan["summary"]["plan_mode"] == "monitoring"
    assert plan["affected_stages"] == []
    assert plan["root_cause_hypotheses"][0]["stage_id"] == "none"
    assert plan["rollback_triggers"][0]["name"] == "new_timeout_detected"


def test_pipeline_stage_timeout_mitigation_plan_sorts_by_severity_then_name() -> None:
    plan = generate_pipeline_stage_timeout_mitigation_plan(
        {
            "stages": [
                {"id": "z", "stage": "Zeta", "timeout_count": 1, "runtime_seconds": 61, "budget_seconds": 60},
                {"id": "b", "stage": "Beta", "timeout_count": 2, "runtime_seconds": 70, "budget_seconds": 60},
                {"id": "a", "stage": "Alpha", "timeout_count": 2, "runtime_seconds": 80, "budget_seconds": 60},
                {"id": "c", "stage": "Critical", "timeout_count": 6, "runtime_seconds": 100, "budget_seconds": 60},
            ]
        }
    )

    assert [(stage["severity"], stage["name"]) for stage in plan["affected_stages"]] == [
        ("critical", "Critical"),
        ("high", "Alpha"),
        ("high", "Beta"),
        ("medium", "Zeta"),
    ]
