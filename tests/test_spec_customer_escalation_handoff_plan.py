from __future__ import annotations

import json

from max.spec.customer_escalation_handoff_plan import generate_customer_escalation_handoff_plan


def test_customer_escalation_handoff_plan_tightens_high_severity() -> None:
    plan = generate_customer_escalation_handoff_plan(
        {
            "project": {"title": "Enterprise Escalation", "buyer": "VP Success"},
            "metadata": {
                "customer_escalation_handoff": {
                    "customer": "Acme",
                    "severity": "sev1",
                    "issues": ["outage", "contract risk"],
                    "owners": ["support lead"],
                    "executive_owner": "CRO",
                }
            },
        }
    )

    assert plan["kind"] == "max.spec.customer_escalation_handoff_plan"
    assert plan["summary"]["customer"] == "Acme"
    assert plan["summary"]["high_severity"] is True
    assert plan["response_timeline"][0]["timing"] == "15 minutes"
    assert plan["owner_assignments"][-1]["owner"] == "CRO"
    assert plan["communication_plan"][1]["description"] == "Run live internal escalation bridge."
    json.dumps(plan)


def test_customer_escalation_handoff_plan_defaults_sparse_input() -> None:
    plan = generate_customer_escalation_handoff_plan({})

    assert plan["summary"]["customer"] == "customer account"
    assert [item["name"] for item in plan["resolution_workstreams"]] == ["open customer escalation"]
    assert plan["response_timeline"][0]["timing"] == "4 business hours"
    assert plan["owner_roles"][-1]["suggested_owner"] == "not_required"
