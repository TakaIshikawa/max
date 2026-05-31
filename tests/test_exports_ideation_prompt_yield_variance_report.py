from __future__ import annotations

import json

from max.exports import generate_ideation_prompt_yield_variance_report
from max.exports.ideation_prompt_yield_variance_report import render_ideation_prompt_yield_variance_report_json, render_ideation_prompt_yield_variance_report_markdown


def test_ideation_prompt_yield_variance_reports_profile_median_variance() -> None:
    report = generate_ideation_prompt_yield_variance_report([{"profile": "p", "prompt_template": "a", "attempts": 10, "generated_units": 8, "approved_units": 4}, {"profile": "p", "prompt_template": "b", "attempts": 10, "generated_units": 2, "approved_units": 1}])

    assert report["rows"][0]["prompt_template"] == "b"
    assert report["rows"][0]["median_yield_rate"] == 0.5
    assert report["summary"]["underperforming_template_count"] == 1
    assert "p / b" in render_ideation_prompt_yield_variance_report_markdown(report)
    json.loads(render_ideation_prompt_yield_variance_report_json(report))
