from __future__ import annotations

import json

from max.spec.source_credential_rotation_plan import generate_source_credential_rotation_plan


def test_source_credential_rotation_plan_prioritizes_credential_health() -> None:
    plan = generate_source_credential_rotation_plan(
        {
            "metadata": {
                "source_credential_rotation": {
                    "credentials": [
                        {"source_name": "zendesk", "credential_id": "cred-healthy", "status": "healthy", "owner": "support_ops"},
                        {"source_name": "salesforce", "credential_id": "cred-expiring", "status": "expiring in 7d", "owner": "crm_ops"},
                        {"source_name": "stripe", "credential_id": "cred-expired", "status": "expired", "owner": "billing_ops"},
                        {"source_name": "s3 lake", "credential_id": "cred-missing", "status": "missing", "owner": "data_ops"},
                    ]
                }
            },
            "evidence": {"source_idea_ids": ["idea-1"]},
        }
    )

    assert plan["title"] == "Source Credential Rotation Plan"
    assert set(plan) >= {"summary", "steps", "validation", "risks", "acceptance_criteria"}
    assert [step["credential_id"] for step in plan["steps"]] == [
        "cred-expired",
        "cred-expiring",
        "cred-missing",
        "cred-healthy",
    ]
    assert plan["steps"][0]["source_name"] == "stripe"
    assert plan["steps"][0]["owner"] == "billing_ops"
    assert plan["steps"][0]["rollback_note"]
    assert plan["validation"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_source_credential_rotation_plan_defaults_and_traceability() -> None:
    plan = generate_source_credential_rotation_plan({})

    assert plan["schema_version"] == "max.spec.source_credential_rotation_plan.v1"
    assert plan["summary"]["credential_count"] == 1
    assert plan["steps"][0]["source_name"] == "primary ingestion source"
    assert plan["steps"][0]["credential_id"] == "source-credential"
    assert plan["steps"][0]["status"] == "missing"
