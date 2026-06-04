from __future__ import annotations

import json

from max.api.insight_synthesis_error_budget_status import insight_synthesis_error_budget_status_to_json


def test_insight_synthesis_error_budget_status_groups_by_profile_then_run() -> None:
    report = json.loads(
        insight_synthesis_error_budget_status_to_json(
            [
                {"profile_id": "p1", "status": "failed"},
                {"profile_id": "p1", "status": "ok"},
                {"run_id": "r1", "status": "ok"},
            ],
            error_budget=0.25,
        )
    )

    assert [row["group_id"] for row in report["groups"]] == ["p1", "r1"]
    assert report["groups"][0]["failure_ratio"] == 0.5
    assert report["groups"][0]["remaining_error_budget"] == 0.0
    assert report["groups"][1]["status"] == "ok"

