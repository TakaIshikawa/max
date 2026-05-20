from __future__ import annotations

import json

from max.exports.llm_budget_variance_report import (
    KIND,
    build_llm_budget_variance_report,
    render_llm_budget_variance_report_json,
)


def test_llm_budget_variance_report_calculates_over_budget_and_models() -> None:
    report = build_llm_budget_variance_report(
        [
            {"run_id": "run-1", "stage": "evaluate", "model": "gpt-a", "budget_tokens": 100, "actual_tokens": 150, "budget_cost": 1.0, "actual_cost": 1.4, "request_count": 2},
            {"run_id": "run-1", "stage": "fetch", "model": "gpt-a", "budget_tokens": 100, "actual_tokens": 90, "budget_cost": 1.0, "actual_cost": 0.8, "request_count": 1, "throttled": "yes"},
            {"run_id": "run-2", "stage": "rank", "model": "gpt-b", "budget_tokens": 0, "actual_tokens": 10, "budget_cost": 0, "actual_cost": 0.2},
        ]
    )

    assert report["kind"] == KIND
    assert report["summary"]["stage_count"] == 3
    assert report["summary"]["over_budget_stage_count"] == 2
    assert report["summary"]["throttled_run_count"] == 1
    assert [row["stage"] for row in report["over_budget_stages"]] == ["evaluate", "rank"]
    assert report["stage_variance"][2]["token_variance_rate"] == 0.0
    assert report["model_totals"][0]["model"] == "gpt-a"
    assert json.loads(render_llm_budget_variance_report_json(report))["summary"]["actual_tokens"] == 250


def test_llm_budget_variance_report_defaults_missing_fields() -> None:
    report = build_llm_budget_variance_report([{}])

    row = report["stage_variance"][0]
    assert row["run_id"] == "unknown-run"
    assert row["stage"] == "unknown-stage"
    assert row["model"] == "unknown-model"
    assert row["token_variance_rate"] == 0.0
    assert report["over_budget_stages"] == []
