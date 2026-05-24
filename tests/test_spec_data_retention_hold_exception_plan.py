from __future__ import annotations

from max.spec.data_retention_hold_exception_plan import (
    KIND,
    generate_data_retention_hold_exception_plan,
)


def test_data_retention_hold_exception_plan_reflects_custom_hints() -> None:
    plan = generate_data_retention_hold_exception_plan(
        {
            "id": "spec-1",
            "project": {"title": "Ledger retention hold"},
            "metadata": {
                "data_retention_hold_exception": {
                    "held_records": [
                        {
                            "dataset": "billing_ledger",
                            "account": "enterprise",
                            "owner": "finance_retention",
                            "duration": "90 days",
                            "legal_basis": "audit inquiry",
                        }
                    ],
                    "hold_rationale": [{"name": "SOX audit request", "duration": "90 days"}],
                    "duration": [{"name": "90 day hold", "duration": "90 days"}],
                    "retention_owner": ["finance_retention"],
                    "controls": ["restrict exports to audit reviewers"],
                    "review_cadence": [{"name": "weekly legal review", "cadence": "weekly"}],
                    "expiry_workflow": [{"name": "release after audit closure", "expiry": "2026-08-01"}],
                }
            },
            "evidence": {"signal_ids": ["hold-evidence"]},
        }
    )

    assert plan["kind"] == KIND
    assert plan["summary"]["title"] == "Ledger retention hold"
    assert plan["summary"]["held_record_count"] == 1
    assert plan["held_records"][0]["name"] == "billing_ledger"
    assert plan["held_records"][0]["duration"] == "90 days"
    assert plan["held_records"][0]["owner"] == "finance_retention"
    assert plan["hold_rationale"][0]["name"] == "SOX audit request"
    assert plan["hold_duration"][0]["duration"] == "90 days"
    assert plan["retention_owner"][0]["name"] == "finance_retention"
    assert plan["controls"][0]["name"] == "restrict exports to audit reviewers"
    assert plan["review_cadence"][0]["cadence"] == "weekly"
    assert plan["expiry_workflow"][0]["expiry"] == "2026-08-01"
    assert plan["evidence_references"][0]["reference"] == "signal:hold-evidence"


def test_data_retention_hold_exception_plan_defaults_are_practical() -> None:
    plan = generate_data_retention_hold_exception_plan({})

    assert set(plan) >= {
        "schema_version",
        "kind",
        "source",
        "summary",
        "held_records",
        "hold_rationale",
        "controls",
        "review_cadence",
        "expiry_workflow",
        "evidence_references",
    }
    assert plan["held_records"][0]["name"] == "records under legal or audit retention hold"
    assert plan["controls"][0]["name"] == "access restriction, encryption, audit logging, and purpose-bound handling"
    assert plan["review_cadence"][0]["name"] == "monthly legal, audit, and privacy review cadence"
