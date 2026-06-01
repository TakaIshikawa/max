from __future__ import annotations

import json

from max.api import pipeline_run_cost_attribution_status_to_json


def test_pipeline_run_cost_attribution_status_summarizes_costs() -> None:
    report = json.loads(
        pipeline_run_cost_attribution_status_to_json(
            {
                "costs": [
                    {"run_id": "r1", "stage": "draft", "cost_usd": 5, "budget_usd": 3, "profile": "p1"},
                    {"run_id": "r2", "stage": "eval", "cost_usd": -2},
                    {"run_id": "r1", "stage": "publish", "cost_usd": 2},
                ]
            },
            as_of="2026-06-01T00:00:00Z",
        )
    )

    assert report["summary"]["status"] == "critical"
    assert report["summary"]["run_count"] == 2
    assert report["summary"]["total_cost_usd"] == 7.0
    assert report["summary"]["unallocated_cost_usd"] == 2.0
    assert report["summary"]["top_cost_driver"] == {"run_id": "r1", "stage": "draft", "cost_usd": 5.0}
    assert [row["stage"] for row in report["attributions"]] == ["draft", "publish", "eval"]
    assert report["status"] == "critical"


def test_pipeline_run_cost_attribution_status_flattens_runs_with_stages() -> None:
    report = json.loads(
        pipeline_run_cost_attribution_status_to_json(
            {"runs": [{"run_id": "r3", "stages": [{"stage": "draft", "cost": "1.25", "profile": "p"}]}]},
            as_of="2026-06-01T00:00:00Z",
        )
    )

    assert report["summary"]["run_count"] == 1
    assert report["summary"]["total_cost_usd"] == 1.25
    assert report["attributions"][0]["run_id"] == "r3"
