from __future__ import annotations

import json

from max.spec import generate_tenant_offboarding_readiness_plan
from max.spec.tenant_offboarding_readiness_plan import KIND, SCHEMA_VERSION


def test_tenant_offboarding_readiness_plan_sorts_and_traces_evidence() -> None:
    plan = generate_tenant_offboarding_readiness_plan(
        _spec(
            "tenant_offboarding_readiness",
            {
                "tenants": [
                    {"name": "Beta", "severity": "low", "deadline_status": "ready"},
                    {"name": "Acme", "severity": "critical", "deadline_status": "missing"},
                    {"name": "Acme", "severity": "critical"},
                ],
                "export_blockers": ["export hold"],
                "deletion_blockers": ["legal retention"],
                "access_revocations": ["admin service account"],
                "stakeholder_handoffs": ["CS owner handoff"],
                "timelines": ["D+30 completion"],
                "evidence": ["audit packet"],
            },
        )
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert [item["name"] for item in plan["tenants"]] == ["Acme", "Beta"]
    assert plan["export_blockers"][0]["evidence_reference_ids"] == ["EV1"]
    assert set(plan) >= {"deletion_blockers", "access_revocations", "stakeholder_handoffs", "timelines", "evidence_checks"}
    assert json.loads(json.dumps(plan)) == plan


def test_tenant_offboarding_readiness_plan_defaults_sparse_input() -> None:
    plan = generate_tenant_offboarding_readiness_plan({})

    assert plan["tenants"][0]["owner"] == "customer_success_owner"
    assert plan["export_blockers"][0]["name"] == "export manifest approval"
    assert plan["deletion_blockers"][0]["name"] == "retention exception review"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"source_idea_ids": ["idea-1"]}}
