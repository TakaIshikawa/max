from __future__ import annotations

from max.exports import generate_llm_token_budget_leak_report


def test_llm_token_budget_leak_report_summarizes_and_sorts_findings() -> None:
    report = generate_llm_token_budget_leak_report(
        [
            {"stage": "draft", "run_id": "r1", "planned_tokens": 100, "prompt_tokens": 80, "completion_tokens": 40},
            {"stage": "rank", "run_id": "r2", "actual_tokens": 50},
            {"stage": "final", "run_id": "r3", "planned_tokens": 100, "actual_tokens": 90},
        ]
    )

    assert report["summary"] == {"planned_tokens": 200, "actual_tokens": 260, "overage_tokens": 60, "overage_ratio": 0.3}
    assert [row["run_id"] for row in report["findings"]] == ["r2", "r1"]
    assert report["findings"][0]["severity"] == "critical"

