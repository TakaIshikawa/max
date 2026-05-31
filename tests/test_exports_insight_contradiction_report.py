from __future__ import annotations

import json

from max.exports import generate_insight_contradiction_report
from max.exports.insight_contradiction_report import render_insight_contradiction_report_json, render_insight_contradiction_report_markdown


def test_insight_contradiction_report_handles_no_contradictions() -> None:
    report = generate_insight_contradiction_report([{"id": "i1", "profile": "p", "market": "us", "category": "crm", "theme": "pricing", "stance": "positive"}])

    assert report["summary"]["contradiction_count"] == 0
    assert "No insight contradictions found." in render_insight_contradiction_report_markdown(report)


def test_insight_contradiction_report_identifies_pair_and_renders_evidence_counts() -> None:
    report = generate_insight_contradiction_report([{"id": "i1", "profile": "p", "market": "us", "category": "crm", "theme": "pricing", "stance": "positive", "confidence": 0.92, "evidence_ids": ["e1", "e2"]}, {"id": "i2", "profile": "p", "market": "us", "category": "crm", "theme": "pricing", "stance": "negative", "confidence": 0.88, "evidence_ids": ["e3", "e4", "e5"]}])

    assert report["rows"][0]["severity"] == "critical"
    assert report["rows"][0]["pairs"][0]["left_id"] == "i1"
    markdown = render_insight_contradiction_report_markdown(report)
    assert "i1 (2 evidence) conflicts with i2 (3 evidence)" in markdown
    json.loads(render_insight_contradiction_report_json(report))


def test_insight_contradiction_report_sorts_by_deterministic_severity() -> None:
    report = generate_insight_contradiction_report([{"id": "w1", "profile": "b", "market": "us", "category": "ops", "theme": "cost", "claim": "yes", "confidence": 0.7, "evidence_count": 1}, {"id": "w2", "profile": "b", "market": "us", "category": "ops", "theme": "cost", "claim": "no", "confidence": 0.7, "evidence_count": 1}, {"id": "c1", "profile": "a", "market": "us", "category": "crm", "theme": "growth", "stance": "increase", "confidence": 0.9, "evidence_count": 2}, {"id": "c2", "profile": "a", "market": "us", "category": "crm", "theme": "growth", "stance": "decrease", "confidence": 0.85, "evidence_count": 3}])

    assert [(row["profile"], row["severity"]) for row in report["rows"]] == [("a", "critical"), ("b", "warn")]
