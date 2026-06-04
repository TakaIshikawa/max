from __future__ import annotations

import json

from max.api.llm_budget_reservation_leak_status import llm_budget_reservation_leak_status_to_json


def test_llm_budget_reservation_leak_status_clamps_and_sorts() -> None:
    parsed = json.loads(
        llm_budget_reservation_leak_status_to_json(
            {
                "reservations": [
                    {"reservation_id": "released", "reserved_tokens": 100, "consumed_tokens": 50, "released_tokens": 50},
                    {"reservation_id": "warning", "reserved_tokens": 100, "consumed_tokens": 70, "released_tokens": 0, "age_minutes": 5},
                    {"reservation_id": "critical", "reserved_tokens": 200, "consumed_tokens": 20, "released_tokens": 0, "age_minutes": 120},
                    {"reservation_id": "zero", "reserved_tokens": 0, "consumed_tokens": -5, "released_tokens": -1, "age_minutes": 999},
                ]
            },
            critical_age_minutes=60,
            warning_leak_ratio=0.2,
        )
    )

    assert [row["reservation_id"] for row in parsed["reservations"]] == ["critical", "warning", "released", "zero"]
    assert [row["status"] for row in parsed["reservations"]] == ["critical", "warning", "ok", "ok"]
    assert parsed["reservations"][-1]["leak_ratio"] == 0.0
    assert parsed["summary"]["total_unreleased_tokens"] == 210
    assert parsed["summary"]["status"] == "critical"
