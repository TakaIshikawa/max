from __future__ import annotations

from max.spec.go_live_decision_record import KIND, SCHEMA_VERSION, generate_go_live_decision_record


def test_go_live_decision_record_approves_clean_readiness() -> None:
    record = generate_go_live_decision_record(
        {
            "metadata": {
                "go_live_decision": {
                    "launch_criteria": [{"name": "SLA accepted", "met": True}],
                    "approvals": [{"role": "SRE", "owner": "sre", "approved": True}],
                    "rollback_ready": True,
                }
            },
            "evidence": {"signal_ids": ["ready-1"]},
        }
    )

    assert record["schema_version"] == SCHEMA_VERSION
    assert record["kind"] == KIND
    assert record["recommendation"] == "approve"
    assert "All launch criteria are met." in record["rationale"]
    assert record["conditions"] == []


def test_go_live_decision_record_conditional_for_open_exceptions() -> None:
    record = generate_go_live_decision_record(
        {
            "launch_criteria": [{"name": "Runbook signed", "met": True}],
            "approvals": [{"role": "Product", "owner": "pm", "approved": False}],
            "rollback_ready": True,
            "open_exceptions": ["dashboard annotation pending"],
        }
    )

    assert record["recommendation"] == "conditional"
    assert [condition["type"] for condition in record["conditions"]] == ["pending_approval", "open_exception"]
    assert record["follow_ups"][0]["action"] == "Track deferred follow-up: dashboard annotation pending"


def test_go_live_decision_record_holds_for_blocking_risks_or_unmet_gates() -> None:
    record = generate_go_live_decision_record(
        {
            "launch_criteria": [{"name": "Rollback rehearsal", "met": False}],
            "risks": [{"name": "data loss risk", "blocking": True}],
            "rollback_ready": False,
        }
    )

    assert record["recommendation"] == "hold"
    assert [condition["type"] for condition in record["conditions"]] == [
        "unmet_gate",
        "blocking_risk",
        "rollback_readiness",
    ]
