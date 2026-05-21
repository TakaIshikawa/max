from __future__ import annotations

import json

from max.spec import generate_data_access_exception_review_plan


def test_data_access_exception_review_plan_sorts_expiry_and_risk() -> None:
    plan = generate_data_access_exception_review_plan(
        _spec(
            "data_access_exception_review",
            {
                "requesters": [
                    {"requester": "Bob", "dataset": "analytics", "severity": "low", "expiry": "2026-10-01"},
                    {"requester": "Alice", "dataset": "payments", "severity": "high", "expiry": "expired"},
                ],
                "datasets": ["payments"],
                "justifications": ["customer escalation"],
                "compensating_controls": ["query logging"],
                "approvers": ["data owner"],
                "expiry": ["7 day review"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.data_access_exception_review_plan.v1"
    assert [item["name"] for item in plan["access_exceptions"]] == ["Alice", "Bob"]
    assert plan["access_exceptions"][0]["dataset"] == "payments"
    assert plan["compensating_controls"][0]["evidence_reference_ids"] == ["EV1"]
    assert set(plan) >= {"access_scope", "justifications", "approval_gates", "expiry_reviews"}
    assert json.loads(json.dumps(plan)) == plan


def test_data_access_exception_review_plan_defaults_sparse_input() -> None:
    plan = generate_data_access_exception_review_plan({})

    assert plan["access_exceptions"][0]["owner"] == "security_owner"
    assert plan["expiry_reviews"][0]["name"] == "access revocation date"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"insight_ids": ["access-1"]}}
