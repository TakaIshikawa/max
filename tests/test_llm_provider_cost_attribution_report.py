from __future__ import annotations

import json

from max.exports import build_llm_provider_cost_attribution_report_export, render_llm_provider_cost_attribution_report_markdown
from max.exports.llm_provider_cost_attribution_report import render_llm_provider_cost_attribution_report_json


def test_llm_provider_cost_attribution_groups_and_sorts_costs() -> None:
    report = build_llm_provider_cost_attribution_report_export([
        {"unit_id": "u1", "provider": "openai", "model": "gpt-4.1", "stage": "spec", "domain": "devtools", "input_tokens": 100, "output_tokens": 50, "estimated_cost_usd": 1.2, "budget_id": "b1", "budget_usd": 1.0},
        {"unit_id": "u2", "provider": "anthropic", "model": "claude", "stage": "ideas", "domain": "devtools", "total_tokens": 20, "estimated_cost_usd": 0.2},
        {"unit_id": "u3", "provider": "openai", "model": "gpt-4.1", "stage": "spec", "domain": "ops", "total_tokens": 10, "estimated_cost_usd": 0.4},
    ])

    assert report["schema_version"] == "max.llm_provider_cost_attribution_report.v1"
    assert report["summary"]["estimated_cost_usd"] == 1.8
    assert report["provider_rows"][0]["provider"] == "openai"
    assert report["model_rows"][0]["model"] == "gpt-4.1"
    assert report["summary"]["over_budget_count"] == 1
    assert "openai / gpt-4.1" in render_llm_provider_cost_attribution_report_markdown(report)
    assert json.loads(render_llm_provider_cost_attribution_report_json(report))["kind"] == "max.llm_provider_cost_attribution_report"


def test_llm_provider_cost_attribution_empty_markdown() -> None:
    assert "No LLM usage records supplied" in render_llm_provider_cost_attribution_report_markdown(build_llm_provider_cost_attribution_report_export([]))
