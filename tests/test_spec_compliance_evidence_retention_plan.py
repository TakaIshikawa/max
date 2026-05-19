from __future__ import annotations

import json

from max.spec.compliance_evidence_retention_plan import generate_compliance_evidence_retention_plan


def test_compliance_evidence_retention_plan_tightens_legal_hold_and_restricted_access() -> None:
    plan = generate_compliance_evidence_retention_plan(
        {
            "project": {"title": "Audit Workspace"},
            "metadata": {
                "compliance_evidence_retention": {
                    "frameworks": ["ISO 27001", "SOC 2"],
                    "evidence_types": ["screenshots"],
                    "retention_period": "10 years",
                    "legal_hold": True,
                    "restricted_access": True,
                }
            },
        }
    )

    assert plan["kind"] == "max.spec.compliance_evidence_retention_plan"
    assert plan["summary"]["frameworks"] == ["ISO 27001", "SOC 2"]
    assert plan["summary"]["retention_period"] == "10 years"
    assert plan["access_controls"][0]["severity"] == "high"
    assert plan["disposal_workflow"][1]["severity"] == "critical"
    assert "Block disposal" in plan["disposal_workflow"][1]["description"]
    json.dumps(plan)


def test_compliance_evidence_retention_plan_defaults_sparse_input() -> None:
    plan = generate_compliance_evidence_retention_plan({})

    assert plan["summary"]["frameworks"] == ["SOC 2"]
    assert [item["name"] for item in plan["evidence_categories"]] == ["approval records", "control test results", "system exports"]
    assert plan["summary"]["retention_period"] == "7 years"
    assert len(plan["owner_roles"]) == 4
