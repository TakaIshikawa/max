from __future__ import annotations

import json

from max.api.budget_reservation_exhaustion_status import budget_reservation_exhaustion_status_to_json


def test_budget_reservation_exhaustion_status_computes_risk_ratios() -> None:
    report = json.loads(
        budget_reservation_exhaustion_status_to_json(
            {
                "reservations": [
                    {"stage": "fetch", "profile": "p", "budget": 100, "reserved": 40, "spent": 20},
                    {"stage": "synthesis", "profile": "p", "budget": 100, "reserved": 97, "spent": 50},
                    {"stage": "eval", "profile": "p", "budget": 100, "reserved": 120, "spent": 10},
                    {"stage": "bad", "profile": "p", "budget": 0, "reserved": -1, "spent": 0},
                ]
            },
            warning_remaining_ratio=0.2,
            critical_remaining_ratio=0.05,
        )
    )

    assert report["rows"][0]["stage"] == "eval"
    assert report["rows"][0]["over_reserved"] is True
    assert report["rows"][1]["stage"] == "synthesis"
    assert report["rows"][1]["remaining_ratio"] == 0.03
    assert report["summary"]["invalid_budget_count"] == 1
    assert report["summary"]["severity"] == "critical"
