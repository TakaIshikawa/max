from __future__ import annotations

import json

from max.exports import generate_source_adapter_error_budget_breach_report
from max.exports.source_adapter_error_budget_breach_report import render_source_adapter_error_budget_breach_report_json, render_source_adapter_error_budget_breach_report_markdown


def test_source_adapter_error_budget_breach_omits_non_breaches_unless_requested() -> None:
    report = generate_source_adapter_error_budget_breach_report([{"adapter": "crm", "profile": "p", "window": "d", "request_count": 100, "error_count": 5, "budget_error_rate": 0.02}, {"adapter": "web", "profile": "p", "window": "d", "request_count": 100, "error_count": 1, "budget_error_rate": 0.02}])
    all_report = generate_source_adapter_error_budget_breach_report([{"adapter": "web", "profile": "p", "window": "d", "request_count": 100, "error_count": 1, "budget_error_rate": 0.02}], include_all=True)

    assert [row["adapter"] for row in report["rows"]] == ["crm"]
    assert all_report["rows"][0]["severity"] == "ok"
    assert render_source_adapter_error_budget_breach_report_markdown(generate_source_adapter_error_budget_breach_report([])).strip().endswith("No error budget breaches found.")
    json.loads(render_source_adapter_error_budget_breach_report_json(report))
