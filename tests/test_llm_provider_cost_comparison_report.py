from __future__ import annotations

import json

from max.exports.llm_provider_cost_comparison_report import (
    build_llm_provider_cost_comparison_report,
    render_llm_provider_cost_comparison_report_json,
    render_llm_provider_cost_comparison_report_markdown,
)


def test_llm_provider_cost_comparison_report_derives_cost_rates() -> None:
    report = build_llm_provider_cost_comparison_report(
        [
            {"provider": "B", "model": "m2", "cost_usd": 0, "token_count": 0, "request_count": 0},
            {"provider": "A", "model": "m1", "cost_usd": 12, "token_count": 6000, "request_count": 3, "baseline_cost_usd": 10},
        ]
    )

    assert report["summary"]["total_cost_usd"] == 12
    assert report["summary"]["highest_cost_provider"] == "A"
    assert report["provider_model_costs"][0]["average_cost_per_request"] == 4
    assert report["provider_model_costs"][0]["cost_per_1k_tokens"] == 2
    assert report["provider_model_costs"][1]["cost_per_1k_tokens"] == 0
    assert "## Summary" in render_llm_provider_cost_comparison_report_markdown(report)
    assert json.loads(render_llm_provider_cost_comparison_report_json(report))["summary"]["request_count"] == 3
