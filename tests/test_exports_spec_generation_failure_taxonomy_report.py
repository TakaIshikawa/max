from __future__ import annotations

import json

from max.exports import generate_spec_generation_failure_taxonomy_report
from max.exports.spec_generation_failure_taxonomy_report import render_spec_generation_failure_taxonomy_report_json, render_spec_generation_failure_taxonomy_report_markdown


def test_spec_generation_failure_taxonomy_accepts_aliases_and_sorts() -> None:
    report = generate_spec_generation_failure_taxonomy_report([{"profile": "p", "generator": "g", "error_code": "parse", "stage": "render", "last_seen_at": "2026-05-30"}, {"profile": "p", "generator": "g", "category": "parse", "stage": "render", "retryable": True, "last_seen_at": "2026-05-31"}, {"profile": "p", "generator": "g", "failure_type": "parse", "stage": "render"}])

    assert report["rows"][0]["failure_count"] == 3
    assert report["rows"][0]["severity"] == "critical"
    assert report["summary"]["retryable_failure_count"] == 1
    assert "p / g / parse / render" in render_spec_generation_failure_taxonomy_report_markdown(report)
    json.loads(render_spec_generation_failure_taxonomy_report_json(report))
