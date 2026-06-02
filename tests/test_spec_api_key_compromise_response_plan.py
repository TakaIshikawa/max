from __future__ import annotations

import json

from max.spec import generate_api_key_compromise_response_plan


def test_api_key_compromise_response_plan_accepts_caller_context() -> None:
    plan = generate_api_key_compromise_response_plan(
        compromised_key_ids=["key-live-1"],
        services=["billing", "publisher"],
        detection_source="GitHub secret scanning",
        containment_deadline="2026-06-01T01:00:00Z",
        approvers=["security", "platform"],
    )

    assert plan["schema_version"] == "max.spec.api_key_compromise_response_plan.v1"
    assert plan["scope"]["compromised_key_ids"] == ["key-live-1"]
    assert plan["scope"]["services"] == ["billing", "publisher"]
    assert plan["scope"]["detection_source"] == "GitHub secret scanning"
    assert [section["id"] for section in plan["sections"]] == [
        "affected_credentials",
        "containment_actions",
        "customer_impact",
        "evidence_preservation",
        "rotation_validation",
        "monitoring",
        "post_incident_follow_up",
    ]
    assert plan["approvers"] == ["security", "platform"]
    assert json.loads(json.dumps(plan)) == plan


def test_api_key_compromise_response_plan_defaults_useful_placeholders() -> None:
    plan = generate_api_key_compromise_response_plan({"evidence": {"signal_ids": ["sig-1"]}})

    assert plan["scope"]["compromised_key_ids"] == ["unknown-key"]
    assert plan["scope"]["services"] == ["affected-service"]
    assert plan["sections"][0]["items"][0]["name"] == "unknown-key"
    assert plan["validation_steps"] == ["revoked_key_authentication_fails", "replacement_key_deployed", "monitoring_alerts_enabled"]
