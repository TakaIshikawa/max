from __future__ import annotations

from max.exports.budget_overrun_root_cause_report import (
    build_budget_overrun_root_cause_report,
    render_budget_overrun_root_cause_report_markdown,
)


def test_budget_overrun_root_cause_report_ranks_contributors() -> None:
    report = build_budget_overrun_root_cause_report(
        [
            {"stage": "evaluate", "adapter": "openai", "model": "gpt-a", "budget_tokens": 100, "actual_tokens": 150, "budget_cost": 1, "actual_cost": 1.5, "retry_count": 2, "retry_cost": 0.2},
            {"stage": "fetch", "adapter": "rss", "model": "none", "budget_tokens": 100, "actual_tokens": 90, "budget_cost": 1, "actual_cost": 0.8},
        ]
    )

    assert report["summary"]["is_over_budget"] is True
    assert report["summary"]["overrun_cost"] == 0.5
    assert report["root_cause_ranking"][0]["stage"] == "evaluate"
    assert report["retry_contribution"]["retry_count"] == 2
    assert "Root-Cause Ranking" in render_budget_overrun_root_cause_report_markdown(report)


def test_budget_overrun_root_cause_report_handles_under_budget_input() -> None:
    report = build_budget_overrun_root_cause_report([{"stage": "fetch", "budget_cost": 2, "actual_cost": 1}])

    assert report["summary"]["is_over_budget"] is False
    assert report["root_cause_ranking"] == []
    assert report["recommended_guardrails"] == ["No budget overrun detected; keep current guardrails."]
