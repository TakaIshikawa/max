from __future__ import annotations

import json

from max.api.llm_budget_reservation_status import llm_budget_reservation_status_to_json


def test_llm_budget_reservation_status_normalizes_numbers_and_risk() -> None:
    parsed = json.loads(
        llm_budget_reservation_status_to_json(
            {
                "reservations": [
                    {"id": "r1", "stage": "draft", "model": "m1", "requested_tokens": "100", "reserved_tokens": "150", "used_tokens": "75"},
                    {"id": "r2", "pipeline_stage": "eval", "model": "m2", "reserved_tokens": "bad", "used_tokens": 10, "cost_cap_usd": "1", "spent_usd": "2"},
                ]
            }
        )
    )

    assert parsed["schema_version"] == "max.api.llm_budget_reservation_status.v1"
    assert parsed["summary"]["reservation_count"] == 2
    assert parsed["summary"]["reserved_tokens"] == 150
    assert parsed["summary"]["used_tokens"] == 85
    assert parsed["summary"]["remaining_tokens"] == 75
    assert parsed["summary"]["risky_count"] == 2
    assert [row["id"] for row in parsed["risky_reservations"]] == ["r1", "r2"]


def test_llm_budget_reservation_status_aliases_totals_and_metadata() -> None:
    parsed = json.loads(llm_budget_reservation_status_to_json({"budget_reservations": [{"reservation_id": "r", "pipeline_stage": "draft", "model": "m", "tokens_reserved": "20", "tokens_used": "5"}]}, as_of="2026-05-21T00:00:00Z"))

    assert parsed["reservations"][0]["utilization_ratio"] == 0.25
    assert parsed["status_totals"][0]["status"] == "reserved"
    assert parsed["stage_totals"][0]["pipeline_stage"] == "draft"
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
