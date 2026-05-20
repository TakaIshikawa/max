from __future__ import annotations

import json

from max.spec import generate_incident_escalation_readiness_plan
from max.spec.incident_escalation_readiness_plan import KIND, SCHEMA_VERSION


def test_incident_escalation_readiness_plan_uses_hints_and_evidence() -> None:
    plan = generate_incident_escalation_readiness_plan(
        _spec(
            {
                "escalation_tiers": [{"name": "legal escalation", "owner": "legal"}],
                "trigger_conditions": ["data exposure"],
                "channels": ["war room", "pager"],
                "response_targets": [{"name": "exec ack", "target_time": "10 minutes"}],
                "validation_checks": ["pager drill"],
            }
        )
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["escalation_tiers"][0]["owner"] == "legal"
    assert [item["channel"] for item in plan["communication_channels"]] == ["pager", "war room"]
    assert plan["response_targets"][0]["timing"] == "10 minutes"
    assert plan["validation_checks"][0]["evidence_reference_ids"] == ["EV1", "EV2"]
    assert json.loads(json.dumps(plan)) == plan


def test_incident_escalation_readiness_plan_defaults_sparse_input() -> None:
    plan = generate_incident_escalation_readiness_plan({})

    assert plan["summary"]["tier_count"] == 2
    assert plan["trigger_conditions"][0]["name"] == "customer-impacting incident"
    assert plan["communication_channels"][0]["channel"] == "incident bridge"
    assert json.loads(json.dumps(plan)) == plan


def _spec(hints: dict) -> dict:
    return {
        "source": {"idea_id": "idea-1"},
        "project": {"title": "Incident Ready", "specific_user": "admins", "workflow_context": "admin launch"},
        "execution": {"risks": ["privacy incident"]},
        "metadata": {"incident_escalation_readiness": hints},
        "evidence": {"insight_ids": ["ins-1"], "signal_ids": ["sig-1"]},
    }
