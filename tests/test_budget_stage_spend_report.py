from __future__ import annotations

from max.exports import generate_budget_stage_spend_report as exported
from max.exports.budget_stage_spend_report import generate_budget_stage_spend_report


def test_budget_stage_spend_report_rolls_up_spend_and_budget_share() -> None:
    report = generate_budget_stage_spend_report(
        [
            {"stage": "synthesis", "profile": "growth", "model": "gpt-a", "input_tokens": 100, "output_tokens": 50, "cost_usd": 12},
            {"stage": "synthesis", "profile": "growth", "model": "gpt-a", "tokens": 50, "cost": 8},
            {"stage": "evaluation", "profile": "growth", "model": "gpt-b", "total_tokens": 100, "total_cost": 5},
        ],
        total_budget=100,
        spend_share_threshold=0.5,
        absolute_cost_threshold=50,
    )

    assert exported is generate_budget_stage_spend_report
    assert report["summary"]["total_tokens"] == 300
    assert report["summary"]["total_cost"] == 25
    assert report["summary"]["breach_count"] == 0
    synthesis = next(row for row in report["rows"] if row["stage"] == "synthesis")
    assert synthesis["total_tokens"] == 200
    assert synthesis["total_cost"] == 20
    assert synthesis["budget_share"] == 0.2
    assert synthesis["status"] == "ok"


def test_budget_stage_spend_report_flags_threshold_breaches_deterministically() -> None:
    report = generate_budget_stage_spend_report(
        [
            {"stage": "expensive", "profile": "core", "model": "gpt-a", "tokens": 1000, "cost": 70},
            {"stage": "cheap", "profile": "core", "model": "gpt-b", "tokens": 100, "cost": 5},
        ],
        total_budget=100,
        spend_share_threshold=0.5,
        absolute_cost_threshold=50,
    )

    assert report["rows"][0]["stage"] == "expensive"
    assert report["rows"][0]["threshold_breaches"] == ["spend_share", "absolute_cost"]
    assert report["rows"][0]["status"] == "breach"

