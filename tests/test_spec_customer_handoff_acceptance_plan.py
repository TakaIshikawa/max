from __future__ import annotations

from max.spec.customer_handoff_acceptance_plan import KIND, SCHEMA_VERSION, generate_customer_handoff_acceptance_plan


def test_customer_handoff_acceptance_blocks_on_blocking_open_item() -> None:
    plan = generate_customer_handoff_acceptance_plan(
        {
            "evidence": {"signal_ids": ["sig-1"]},
            "metadata": {
                "customer_handoff_acceptance": {
                    "receiving_teams": [{"name": "Customer Success", "owner": "CS Lead"}],
                    "open_items": [{"name": "contract addendum", "severity": "blocking"}],
                    "signoffs": [{"name": "customer owner", "status": "approved"}],
                }
            },
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["handoff_status"] == "blocked"
    assert plan["receiving_teams"][0]["owner"] == "CS Lead"
    assert plan["receiving_teams"][0]["evidence_reference_ids"] == ["EV1"]


def test_customer_handoff_acceptance_pending_for_missing_signoff() -> None:
    plan = generate_customer_handoff_acceptance_plan({"metadata": {"customer_handoff_acceptance": {"checks": ["runbook accepted"]}}})

    assert plan["handoff_status"] == "pending"
    assert plan["signoffs"][0]["status"] == "required"
