from __future__ import annotations

import json

from max.spec import generate_access_recertification_exception_plan


def test_access_recertification_exception_plan_uses_hints() -> None:
    plan = generate_access_recertification_exception_plan(
        _spec(
            {
                "exception_subjects": ["ops user"],
                "access_scopes": ["prod admin"],
                "business_justification": ["incident coverage"],
                "expiry_date": "2026-06-30",
                "compensating_controls": [{"name": "session recording", "owner": "sec"}],
                "approvers": ["CISO"],
                "review_cadence": "daily",
                "validation_checks": ["approval audit"],
            }
        )
    )

    assert plan["review_cadence"]["cadence"] == "daily"
    assert plan["review_cadence"]["expiry"] == "2026-06-30"
    assert plan["compensating_controls"][0]["owner"] == "sec"
    assert plan["validation_checks"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_access_recertification_exception_plan_defaults_sparse_input() -> None:
    plan = generate_access_recertification_exception_plan({})

    assert plan["exception_subjects"][0]["name"] == "primary user"
    assert plan["review_cadence"]["cadence"] == "monthly"
    assert json.loads(json.dumps(plan)) == plan


def _spec(hints: dict) -> dict:
    return {"metadata": {"access_recertification_exception": hints}, "evidence": {"insight_ids": ["ins-1"]}}
