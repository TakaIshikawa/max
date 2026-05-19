from __future__ import annotations

import json

from max.spec.privacy_incident_notification_plan import (
    KIND,
    PRIVACY_INCIDENT_NOTIFICATION_PLAN_SCHEMA_VERSION,
    generate_privacy_incident_notification_plan,
)


def _spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "privacy-incident-1", "domain": "privacy"},
        "project": {
            "title": "Customer Account Portal",
            "workflow_context": "customer account management",
            "specific_user": "account holder",
            "buyer": "privacy director",
        },
        "execution": {
            "mvp_scope": ["account database", "support exports"],
            "risks": ["Potential unauthorized exposure of PII and payment notes."],
        },
        "metadata": {
            "regulatory_regions": ["GDPR", "CPRA"],
            "privacy_incident": {
                "type": "unauthorized export exposure",
                "severity": "critical",
                "high_risk": True,
                "affected_data_subjects": ["EU customers", "California customers"],
                "data_categories": ["email", "payment notes"],
                "systems": ["support export job"],
                "discovery_time": "2026-05-20T09:00:00Z",
            },
        },
        "evidence": {
            "insight_ids": ["ins-privacy"],
            "signal_ids": ["sig-export"],
            "rationale": "Support export may have exposed regulated customer data.",
        },
    }


def test_privacy_incident_notification_plan_complete_shape_and_strict_deadlines() -> None:
    plan = generate_privacy_incident_notification_plan(_spec())

    assert plan["schema_version"] == PRIVACY_INCIDENT_NOTIFICATION_PLAN_SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["source"]["idea_id"] == "privacy-incident-1"
    assert plan["summary"]["title"] == "Customer Account Portal"
    assert plan["summary"]["notification_strictness"] == "strict"
    assert plan["summary"]["notification_deadline"] == "72 hours from confirmation"
    assert plan["summary"]["customer_communication_cadence"] == "twice daily until notifications are complete"
    assert plan["notification_strategy"]["incident_type"] == "unauthorized export exposure"
    assert set(plan) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "notification_strategy",
        "affected_data_subjects",
        "regulatory_deadlines",
        "customer_comms",
        "evidence_preservation",
        "owner_roles",
        "evidence_references",
    }

    assert [item["segment"] for item in plan["affected_data_subjects"]] == [
        "California customers",
        "EU customers",
    ]
    assert [item["deadline"] for item in plan["regulatory_deadlines"]] == [
        "72 hours from confirmation",
        "without undue delay after notice approval",
    ]
    assert [item["milestone"] for item in plan["customer_comms"]] == [
        "within 24 hours",
        "within 72 hours",
        "twice daily until notifications are complete",
    ]
    assert [item["id"] for item in plan["evidence_preservation"]] == ["EP1", "EP2", "EP3"]
    assert {item["role"] for item in plan["owner_roles"]} == {
        "incident_commander",
        "privacy_owner",
        "legal_owner",
        "communications_owner",
        "data_owner",
    }
    assert [item["reference"] for item in plan["evidence_references"]] == [
        "insight:ins-privacy",
        "signal:sig-export",
        "Support export may have exposed regulated customer data.",
    ]
    assert json.loads(json.dumps(plan))["kind"] == KIND


def test_privacy_incident_notification_plan_sparse_input_defaults() -> None:
    plan = generate_privacy_incident_notification_plan({})

    assert plan["summary"]["title"] == "Untitled TactSpec"
    assert plan["summary"]["notification_strictness"] == "standard"
    assert plan["summary"]["incident_type"] == "potential privacy incident"
    assert plan["summary"]["regulated_regions"] == ["unconfirmed operating region"]
    assert plan["notification_strategy"]["decision_deadline"] == "5 business days from confirmation"
    assert plan["affected_data_subjects"][0]["segment"] == "primary user"
    assert [item["milestone"] for item in plan["customer_comms"]] == [
        "within 2 business days",
        "daily until closure",
    ]
    assert plan["evidence_references"] == []


def test_privacy_incident_notification_plan_is_deterministic() -> None:
    first = generate_privacy_incident_notification_plan(_spec())
    second = generate_privacy_incident_notification_plan(_spec())

    assert first == second
