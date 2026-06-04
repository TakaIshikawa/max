from __future__ import annotations

import json

from max.api.llm_budget_reservation_leak_status import llm_budget_reservation_leak_status_to_json


def test_llm_budget_reservation_leak_status_excludes_released_and_flags_stale() -> None:
    report = json.loads(
        llm_budget_reservation_leak_status_to_json(
            [
                {"reservation_id": "released", "reserved_amount": 100, "spent_amount": 0, "released_at": "2026-01-01T23:00:00Z"},
                {"reservation_id": "warning", "reserved_amount": 100, "spent_amount": 70, "created_at": "2026-01-01T23:50:00Z"},
                {"reservation_id": "critical", "reserved_amount": 200, "spent_amount": 20, "created_at": "2026-01-01T22:00:00Z", "status": "reserved"},
            ],
            now="2026-01-02T00:00:00Z",
            stale_after_minutes=60,
            warning_leak_ratio=0.2,
        )
    )

    assert [row["reservation_id"] for row in report["reservations"]] == ["critical", "warning", "released"]
    assert report["summary"]["active_reservation_count"] == 2
    assert report["summary"]["total_leaked_amount"] == 210.0
    assert report["reservations"][-1]["leaked_amount"] == 0.0
