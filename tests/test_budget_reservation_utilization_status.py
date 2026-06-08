from __future__ import annotations

import json

from max.api import budget_reservation_utilization_status_to_json as exported
from max.api.budget_reservation_utilization_status import budget_reservation_utilization_status_to_json


def test_budget_reservation_utilization_status_handles_empty_reservations() -> None:
    report = json.loads(budget_reservation_utilization_status_to_json([]))

    assert exported is budget_reservation_utilization_status_to_json
    assert report["summary"]["status"] == "efficient"
    assert report["summary"]["reserved_amount"] == 0
    assert report["reservations"] == []


def test_budget_reservation_utilization_status_groups_and_clamps_unused() -> None:
    report = json.loads(
        budget_reservation_utilization_status_to_json(
            [
                {"profile": "core", "pipeline_stage": "fetch", "reserved_amount": 100, "consumed_amount": 30},
                {"profile": "core", "pipeline_stage": "fetch", "reserved_amount": 50, "consumed_amount": 200, "expired": True},
                {"profile": "core", "pipeline_stage": "publish", "reserved_amount": 100, "consumed_amount": 100},
            ]
        )
    )

    assert [row["pipeline_stage"] for row in report["reservations"]] == ["fetch", "publish"]
    assert report["reservations"][0]["reserved_amount"] == 150
    assert report["reservations"][0]["unused_amount"] == 0
    assert report["reservations"][0]["utilization_percent"] == 100
    assert report["reservations"][0]["expired_reservation_count"] == 1


def test_budget_reservation_utilization_status_classifies_underused() -> None:
    report = json.loads(budget_reservation_utilization_status_to_json({"reservations": [{"profile": "lab", "stage": "score", "reserved": 100, "consumed": 10}]}))

    assert report["reservations"][0]["status"] == "underused"
    assert report["summary"]["status"] == "underused"
