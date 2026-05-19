from __future__ import annotations

import json

from max.spec.on_call_handoff_plan import generate_on_call_handoff_plan


def test_on_call_handoff_plan_reflects_issue_dashboard_alert_and_policy_hints() -> None:
    plan = generate_on_call_handoff_plan(
        {
            "metadata": {
                "on_call_handoff": {
                    "services": ["api"],
                    "current_owner": "Ari",
                    "next_owner": "Blair",
                    "escalation_policy": "payments-sev1",
                    "known_issues": ["elevated latency"],
                    "dashboards": ["api health"],
                    "alerts": ["latency page"],
                }
            }
        }
    )

    assert plan["kind"] == "max.spec.on_call_handoff_plan"
    assert plan["summary"]["next_owner"] == "Blair"
    assert plan["summary"]["escalation_policy"] == "payments-sev1"
    assert plan["active_risks"][0]["name"] == "elevated latency"
    assert plan["escalation_paths"][0]["severity"] == "high"
    assert [item["name"] for item in plan["runbook_checklist"]] == ["api health", "latency page"]
    json.dumps(plan)


def test_on_call_handoff_plan_defaults_sparse_input() -> None:
    plan = generate_on_call_handoff_plan({})

    assert plan["summary"]["service_count"] == 1
    assert [item["name"] for item in plan["service_coverage"]] == ["primary service"]
    assert plan["active_risks"][0]["name"] == "no_known_issues"
    assert len(plan["shift_transition_steps"]) == 3
