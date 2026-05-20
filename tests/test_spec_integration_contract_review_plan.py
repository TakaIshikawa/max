from __future__ import annotations

import json

from max.spec.integration_contract_review_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_integration_contract_review_plan,
)


def test_integration_contract_review_plan_groups_multiple_integrations() -> None:
    plan = generate_integration_contract_review_plan(
        {
            "source": {"idea_id": "contract-1"},
            "project": {"title": "Partner Sync"},
            "metadata": {
                "integration_contract_review": {
                    "integrations": [
                        {"name": "CRM API", "owner": "revops", "acceptance_signal": "CRM sandbox contract passes"},
                        {"name": "Billing Webhook", "owner": "billing"},
                    ],
                    "dependencies": [{"name": "Identity Provider", "owner": "security", "priority": "high"}],
                }
            },
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert [group["name"] for group in plan["contract_checks"]] == ["Billing Webhook", "CRM API", "Identity Provider"]
    assert all({"owner", "priority", "acceptance_signal", "evidence_reference_ids"} <= set(group) for group in plan["contract_checks"])
    assert plan["contract_checks"][1]["acceptance_signal"] == "CRM sandbox contract passes"
    assert len(plan["contract_checks"][0]["checks"]) == 3
    json.dumps(plan)


def test_integration_contract_review_plan_surfaces_missing_owners() -> None:
    plan = generate_integration_contract_review_plan({"integrations": ["Search API"]})

    assert plan["summary"]["missing_owner_count"] == 1
    assert plan["contract_checks"][0]["owner"] == "integration_owner"
    assert plan["follow_up_actions"] == [
        {
            "id": "FU1",
            "type": "missing_owner",
            "target": "Search API",
            "owner": "release_manager",
            "priority": "high",
            "action": "Assign a named owner for Search API before contract review signoff.",
            "acceptance_signal": "Named owner is recorded in the review plan.",
            "evidence_reference_ids": [],
        }
    ]


def test_integration_contract_review_plan_propagates_evidence_ids() -> None:
    plan = generate_integration_contract_review_plan(
        {
            "integrations": [{"name": "ERP API", "owner": "finance"}],
            "evidence": {"signal_ids": ["api-spec"], "source_idea_ids": ["idea-2"]},
        }
    )

    assert plan["contract_checks"][0]["evidence_reference_ids"] == ["EV1", "EV2"]
    assert plan["contract_checks"][0]["checks"][0]["evidence_reference_ids"] == ["EV1", "EV2"]
    assert plan["security_privacy_checks"][0]["evidence_reference_ids"] == ["EV1", "EV2"]
