from __future__ import annotations

from max.spec.compliance_exception_register import KIND, SCHEMA_VERSION, generate_compliance_exception_register


def test_compliance_exception_register_sorts_and_escalates_missing_fields() -> None:
    register = generate_compliance_exception_register(
        {
            "evidence": {"signal_ids": ["sig-1"]},
            "metadata": {
                "compliance_exception_register": {
                    "exceptions": [
                        {"name": "minor exception", "severity": "low", "control": "SOC2-1", "expiration": "2026-12-31", "owner": "Compliance"},
                        {"name": "access exception", "severity": "high", "status": "overdue"},
                    ]
                }
            },
        }
    )

    assert register["schema_version"] == SCHEMA_VERSION
    assert register["kind"] == KIND
    assert register["exceptions"][0]["name"] == "access exception"
    assert register["exceptions"][0]["owner"] == "missing_owner"
    assert register["escalation_items"]
    assert register["exceptions"][0]["evidence_reference_ids"] == ["EV1"]


def test_compliance_exception_register_defaults_review_cadence() -> None:
    register = generate_compliance_exception_register({})

    assert register["review_cadence"] in {"monthly", "weekly"}
    assert register["affected_controls"]
