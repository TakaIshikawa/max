from __future__ import annotations

import json

from max.exports.prompt_injection_attempt_trend_report import (
    build_prompt_injection_attempt_trend_report,
    render_prompt_injection_attempt_trend_report_json,
    render_prompt_injection_attempt_trend_report_markdown,
)


def test_prompt_injection_attempt_trend_report_groups_and_sorts() -> None:
    report = build_prompt_injection_attempt_trend_report(
        [
            {"source": "web", "profile": "P2", "severity": "low", "blocked": False, "occurred_at": "2026-05-26T10:00:00Z"},
            {"source": "api", "profile": "P1", "severity": "critical", "blocked": True, "occurred_at": "2026-05-25T10:00:00Z", "attempt_count": 2},
            {"source": "api", "profile": "P1", "severity": "critical", "blocked": True, "occurred_at": "2026-05-25T12:00:00Z"},
            {"source": "web", "profile": "P1", "severity": "high", "blocked": True, "occurred_at": "2026-05-24"},
        ]
    )

    assert report["summary"]["total_attempt_count"] == 5
    assert report["summary"]["blocked_count"] == 4
    assert report["summary"]["critical_attempt_count"] == 3
    assert [(row["severity"], row["date"], row["source"]) for row in report["attempt_trends"]] == [
        ("critical", "2026-05-25", "api"),
        ("high", "2026-05-24", "web"),
        ("low", "2026-05-26", "web"),
    ]
    assert report["attempt_trends"][0]["attempt_count"] == 3


def test_prompt_injection_attempt_trend_report_renders_and_handles_empty() -> None:
    report = build_prompt_injection_attempt_trend_report([])

    assert report["summary"]["total_attempt_count"] == 0
    assert report["attempt_trends"] == []
    markdown = render_prompt_injection_attempt_trend_report_markdown(report)
    assert "## Summary" in markdown
    assert "- Total attempts: 0" in markdown
    rendered = render_prompt_injection_attempt_trend_report_json(report)
    assert rendered.endswith("\n")
    assert json.loads(rendered)["summary"]["blocked_count"] == 0
