from __future__ import annotations

from max.spec import generate_budget_reservation_recovery_plan


def test_budget_reservation_recovery_plan_detects_exhausted_near_exhausted_and_over_reserved() -> None:
    plan = generate_budget_reservation_recovery_plan(
        {
            "metadata": {
                "budget_reservation_recovery": {
                    "reservations": [
                        {"id": "near", "stage": "draft", "reserved": 100, "used": 90, "limit": 150},
                        {"id": "over", "stage": "eval", "reserved": 200, "used": 40, "limit": 150},
                        {"id": "exhausted", "stage": "publish", "reserved": 100, "used": 100, "limit": 120},
                    ]
                }
            }
        }
    )

    assert [item["id"] for item in plan["reservation_inventory"]] == ["over", "exhausted", "near"]
    assert [item["status"] for item in plan["reservation_inventory"]] == ["over_reserved", "exhausted", "near_exhausted"]
    assert [item["status"] for item in plan["recovery_actions"]] == ["over_reserved", "exhausted", "near_exhausted"]


def test_budget_reservation_recovery_plan_surfaces_negative_or_missing_budget_fields() -> None:
    plan = generate_budget_reservation_recovery_plan({"reservations": [{"id": "bad", "stage": "plan", "reserved": -1, "used": 0}]})

    row = plan["reservation_inventory"][0]
    assert row["status"] == "data_quality_risk"
    assert row["data_quality_risks"] == ["negative_reserved", "missing_limit"]
    assert "Correct missing or invalid" in plan["recovery_actions"][0]["action"]


def test_budget_reservation_recovery_plan_includes_stage_actions_and_guardrail_validation() -> None:
    plan = generate_budget_reservation_recovery_plan({"reservations": [{"id": "ok", "stage": "draft", "reserved": 100, "used": 20, "limit": 100}]})

    assert plan["summary"]["recovery_count"] == 0
    assert plan["recovery_actions"] == []
    assert plan["guardrail_validation"][0]["name"] == "released_budget_matches_pool_delta"
