from __future__ import annotations

import json

from max.spec import generate_privacy_request_escalation_plan


def test_privacy_request_escalation_plan_renders_sla_and_closure() -> None:
    plan = generate_privacy_request_escalation_plan(
        _spec(
            "privacy_request_escalation",
            {
                "requests": [
                    {"requester": "alice@example.com", "request_type": "deletion", "jurisdiction": "GDPR", "severity": "high", "deadline": "2026-06-01"},
                    {"requester": "bob@example.com", "request_type": "access", "jurisdiction": "CCPA", "severity": "low"},
                ],
                "sla_risk": ["5 days remaining"],
                "blockers": ["legal hold review"],
                "evidence_needed": ["identity verification"],
                "owners": ["privacy counsel"],
                "communications": ["requester update"],
                "closure": ["fulfillment receipt"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.privacy_request_escalation_plan.v1"
    assert [item["name"] for item in plan["request_scope"]] == ["alice@example.com", "bob@example.com"]
    assert set(plan) >= {"sla_risk", "blockers", "evidence_needed", "escalation_owners", "communications", "closure_proof"}
    assert json.loads(json.dumps(plan)) == plan


def test_privacy_request_escalation_plan_defaults_blockers_and_evidence() -> None:
    plan = generate_privacy_request_escalation_plan({})

    assert plan["blockers"][0]["name"] == "no active blockers; verify dependencies remain clear"
    assert plan["evidence_needed"][0]["name"] == "identity, scope, fulfillment, and exemption evidence"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"insight_ids": ["pre-1"]}}
