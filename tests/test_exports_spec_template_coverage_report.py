from __future__ import annotations

import json

from max.exports import generate_spec_template_coverage_report
from max.exports.spec_template_coverage_report import render_spec_template_coverage_report_json, render_spec_template_coverage_report_markdown


def test_spec_template_coverage_reports_missing_critical_sections() -> None:
    report = generate_spec_template_coverage_report([{"id": "s1", "template": "launch", "sections": {"objective": "x", "scope": "x", "risks": "x"}}, {"id": "s2", "template": "launch", "objective": "x", "scope": "x", "acceptance_criteria": "x", "evidence": "x", "risks": "x", "rollout": "x"}])

    row = report["rows"][0]
    assert row["coverage_percent"] == 75.0
    assert row["missing_critical_sections"] == ["acceptance_criteria", "evidence"]
    assert row["missing_sections"]["rollout"] == ["s1"]
    assert "missing evidence: s1" in render_spec_template_coverage_report_markdown(report)
    json.loads(render_spec_template_coverage_report_json(report))
