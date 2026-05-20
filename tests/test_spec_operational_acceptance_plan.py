from __future__ import annotations

import json

from max.spec.operational_acceptance_plan import KIND, SCHEMA_VERSION, generate_operational_acceptance_plan


def test_operational_acceptance_plan_derives_gates_and_preserves_evidence() -> None:
    plan = generate_operational_acceptance_plan(
        {
            "source": {"idea_id": "ops-accept-1"},
            "project": {"title": "Checkout Launch", "buyer": "Ops Council"},
            "metadata": {
                "operational_acceptance": {
                    "systems": ["Payments API", "Checkout Worker"],
                    "runbooks": ["Checkout incident runbook"],
                    "owners": {"Payments API": "payments_ops", "default": "platform_ops"},
                    "risks": [
                        {"name": "pager route missing", "severity": "high", "description": "Pager route is not mapped."},
                        {"name": "dashboard label cleanup", "severity": "low"},
                    ],
                }
            },
            "evidence": {"signal_ids": ["sig-1"], "insight_ids": ["ins-7", "ins-7"]},
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["title"] == "Checkout Launch Operational Acceptance Plan"
    assert [gate["name"] for gate in plan["gates"]] == ["Checkout Worker", "Payments API", "Checkout incident runbook"]
    assert plan["gates"][1]["owner"] == "payments_ops"
    assert plan["gates"][0]["evidence_reference_ids"] == ["EV1", "EV2"]
    assert plan["evidence_references"] == [
        {"id": "EV1", "type": "insight", "reference": "insight:ins-7"},
        {"id": "EV2", "type": "signal", "reference": "signal:sig-1"},
    ]
    json.dumps(plan)


def test_operational_acceptance_plan_defaults_sparse_input() -> None:
    plan = generate_operational_acceptance_plan({})

    assert plan["summary"]["system_count"] == 1
    assert plan["summary"]["runbook_count"] == 1
    assert plan["gates"][0]["name"] == "Primary service"
    assert plan["gates"][0]["owner"] == "operations_owner"
    assert plan["evidence_requirements"][0]["severity"] == "high"
    assert any(action["type"] == "evidence_setup" for action in plan["next_actions"])


def test_operational_acceptance_plan_orders_blockers_by_severity() -> None:
    plan = generate_operational_acceptance_plan(
        {
            "metadata": {
                "operational_acceptance": {
                    "risks": [
                        {"name": "cosmetic doc gap", "severity": "low"},
                        {"name": "rollback path missing", "severity": "critical"},
                        {"name": "support queue coverage", "severity": "high"},
                    ]
                }
            }
        }
    )

    assert [item["name"] for item in plan["blockers"]] == [
        "rollback path missing",
        "support queue coverage",
        "cosmetic doc gap",
    ]
    assert [item["severity"] for item in plan["blockers"]] == ["critical", "high", "low"]
