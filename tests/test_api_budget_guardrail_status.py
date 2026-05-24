from __future__ import annotations

import json

from max.api.budget_guardrail_status import KIND, SCHEMA_VERSION, budget_guardrail_status_to_json


def test_budget_guardrail_status_derives_remaining_and_breaches() -> None:
    parsed = json.loads(
        budget_guardrail_status_to_json(
            {
                "dimensions": [
                    {"dimension": "cost", "unit": "usd", "limit": 100, "spent": 70, "reserved": 15},
                    {"dimension": "tokens", "limit": 1000, "spent": 1000},
                ],
                "guardrails": [
                    {"dimension": "cost", "soft_limit_percent": 80, "hard_limit_percent": 95},
                    {"dimension": "tokens", "soft_limit_percent": 80, "hard_limit_percent": 100},
                ],
            }
        )
    )

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["dimensions"][0]["remaining"] == 15.0
    assert parsed["dimensions"][0]["utilization_percent"] == 85.0
    assert parsed["breaches"] == [
        {"dimension": "cost", "level": "soft", "message": "soft budget guardrail breached", "utilization_percent": 85.0},
        {"dimension": "tokens", "level": "hard", "message": "hard budget guardrail breached", "utilization_percent": 100.0},
    ]
    assert parsed["budget_summary"]["soft_breach_count"] == 1
    assert parsed["budget_summary"]["hard_breach_count"] == 1
    assert [row["id"] for row in parsed["next_actions"]] == ["review-cost", "review-tokens"]


def test_budget_guardrail_status_honors_explicit_sections() -> None:
    parsed = json.loads(
        budget_guardrail_status_to_json(
            {
                "budgets": [{}],
                "budget_summary": {"total_limit": 9},
                "breaches": [{"dimension": "cost", "level": "soft"}],
                "reservations": [{"id": "r1", "amount": 2}],
                "next_actions": [{"id": "a1"}],
            }
        )
    )

    assert parsed["budget_summary"]["total_limit"] == 9.0
    assert parsed["breaches"][0]["dimension"] == "cost"
    assert parsed["reservations"][0]["id"] == "r1"
    assert parsed["next_actions"][0]["id"] == "a1"
