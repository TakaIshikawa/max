from __future__ import annotations

import json

from max.spec.audit_evidence_collection_plan import generate_audit_evidence_collection_plan


def test_audit_evidence_collection_plan_maps_frameworks_controls_and_tasks() -> None:
    plan = generate_audit_evidence_collection_plan(
        {
            "metadata": {
                "audit_evidence": {
                    "frameworks": ["ISO 27001"],
                    "controls": ["A.5.15"],
                    "systems": ["IAM"],
                    "evidence_types": ["user export", "approval"],
                    "cadence": "monthly",
                    "reviewers": ["GRC"],
                }
            }
        }
    )

    assert plan["kind"] == "max.spec.audit_evidence_collection_plan"
    assert plan["summary"]["frameworks"] == ["ISO 27001"]
    assert plan["summary"]["control_count"] == 1
    assert [item["name"] for item in plan["collection_tasks"]] == ["A.5.15 approval", "A.5.15 user export"]
    assert plan["control_mapping"][0]["references"] == ["ISO 27001"]
    assert plan["reviewer_workflow"][0]["owner"] == "GRC"
    json.dumps(plan)


def test_audit_evidence_collection_plan_defaults_to_quarterly_workflow() -> None:
    plan = generate_audit_evidence_collection_plan({})

    assert plan["summary"]["frameworks"] == ["SOC 2"]
    assert plan["summary"]["collection_cadence"] == "quarterly"
    assert len(plan["collection_tasks"]) == 4
    assert [item["name"] for item in plan["control_mapping"]] == ["access review", "change management"]
