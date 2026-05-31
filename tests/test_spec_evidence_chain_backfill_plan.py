from __future__ import annotations

import json

from max.spec.evidence_chain_backfill_plan import generate_evidence_chain_backfill_plan


def test_evidence_chain_backfill_plan_groups_and_orders_issues() -> None:
    plan = generate_evidence_chain_backfill_plan(
        {
            "metadata": {
                "evidence_chain_backfill": {
                    "issues": [
                        {"entity_type": "unit", "entity_id": "unit-2", "severity": "low"},
                        {"entity_type": "insight", "entity_id": "ins-1", "severity": "critical", "missing_reference": "signal-9"},
                        {"entity_type": "unit", "entity_id": "unit-1", "severity": "high", "repairability": "unrepairable"},
                    ]
                }
            }
        }
    )

    assert plan["title"] == "Evidence Chain Backfill Plan"
    assert [(group["entity_type"], group["severity"]) for group in plan["issue_groups"]] == [
        ("insight", "critical"),
        ("unit", "high"),
        ("unit", "low"),
    ]
    assert plan["repair_order"][0]["entity_id"] == "ins-1"
    assert plan["manual_review"][0]["entity_id"] == "unit-1"
    assert plan["validation_checks"]
    assert plan["acceptance_criteria"]
    assert json.loads(json.dumps(plan)) == plan


def test_evidence_chain_backfill_plan_defaults_empty_input() -> None:
    plan = generate_evidence_chain_backfill_plan({})

    assert plan["summary"]["issue_count"] == 1
    assert plan["issue_groups"][0]["entity_type"] == "insight"
    assert plan["repair_order"][0]["repairability"] == "repairable"
