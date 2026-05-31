from __future__ import annotations

import json

from max.exports import generate_budget_reservation_utilization_report
from max.exports.budget_reservation_utilization_report import render_budget_reservation_utilization_report_json, render_budget_reservation_utilization_report_markdown


def test_budget_reservation_utilization_flags_underuse_and_overrun() -> None:
    report = generate_budget_reservation_utilization_report([{"run_id": "r1", "profile": "p", "stage": "draft", "provider": "openai", "reserved_tokens": 100, "consumed_tokens": 20, "reserved_cost": 1, "consumed_cost": 0.2}, {"run_id": "r2", "profile": "p", "stage": "draft", "provider": "openai", "reserved_tokens": 100, "consumed_tokens": 130}])

    assert report["rows"][0]["run_id"] == "r2"
    assert report["summary"]["underutilized_count"] == 1
    assert report["summary"]["overrun_count"] == 1
    assert "r2 / p / draft / openai" in render_budget_reservation_utilization_report_markdown(report)
    json.loads(render_budget_reservation_utilization_report_json(report))
