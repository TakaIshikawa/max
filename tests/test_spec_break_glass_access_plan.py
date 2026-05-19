from __future__ import annotations

import json

from max.spec.break_glass_access_plan import generate_break_glass_access_plan


def test_break_glass_access_plan_uses_mfa_ticket_and_duration_hints() -> None:
    plan = generate_break_glass_access_plan(
        {
            "metadata": {
                "break_glass": {
                    "systems": ["prod-db"],
                    "roles": ["SRE"],
                    "approvers": ["security lead"],
                    "max_duration": "30 minutes",
                    "mfa_required": True,
                    "ticket_required": True,
                    "audit_log": "SIEM",
                }
            }
        }
    )

    assert plan["kind"] == "max.spec.break_glass_access_plan"
    assert plan["summary"]["max_duration"] == "30 minutes"
    assert plan["approval_flow"][1]["name"] == "ticket_gate"
    assert plan["approval_flow"][2]["description"] == "MFA verification is mandatory before access is granted."
    assert plan["revocation_steps"][0]["description"] == "Automatically revoke access at 30 minutes."
    assert "SIEM" in plan["monitoring_requirements"][1]["description"]
    json.dumps(plan)


def test_break_glass_access_plan_defaults_sparse_input() -> None:
    plan = generate_break_glass_access_plan({})

    assert plan["summary"]["systems"] == ["production environment"]
    assert plan["summary"]["mfa_required"] is True
    assert plan["summary"]["ticket_required"] is True
    assert [item["name"] for item in plan["eligible_roles"]] == ["incident commander", "senior engineer"]
    assert len(plan["audit_requirements"]) == 2
