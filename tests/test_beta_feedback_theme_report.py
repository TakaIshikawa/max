from __future__ import annotations

import json

from max.exports.beta_feedback_theme_report import (
    KIND,
    SCHEMA_VERSION,
    build_beta_feedback_theme_report,
    render_beta_feedback_theme_json,
    render_beta_feedback_theme_markdown,
)


def test_beta_feedback_theme_report_normalizes_groups_and_renders() -> None:
    records = [
        {
            "account": "Acme",
            "segment": "Enterprise",
            "theme": " onboarding flow ",
            "sentiment": "negative",
            "severity": "High",
            "blocker": "yes",
            "submitted_at": "2026-05-01",
            "feedback": "Too many steps",
        },
        {
            "customer": "BetaCo",
            "segment": "SMB",
            "theme": "ONBOARDING   FLOW",
            "sentiment": "mixed",
            "severity": "medium",
            "blocker": False,
            "owner": "product",
            "date": "2026-05-02",
        },
        {
            "account": "Cygnus",
            "segment": "Enterprise",
            "feedback_theme": "reporting",
            "sentiment": "positive",
            "severity": "low",
            "owner": "analytics",
            "blocker": "false",
        },
    ]

    report = build_beta_feedback_theme_report(records)

    assert report == build_beta_feedback_theme_report(records)
    assert json.loads(json.dumps(report)) == report
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"] == {
        "feedback_count": 3,
        "theme_count": 2,
        "segment_count": 2,
        "blocker_count": 1,
        "severe_count": 1,
        "unowned_severe_count": 1,
    }
    assert [row["theme"] for row in report["theme_rows"]] == ["Onboarding Flow", "Reporting"]
    assert report["theme_rows"][0]["feedback_count"] == 2
    assert report["theme_rows"][0]["blocker_count"] == 1
    assert report["segment_breakdown"][0]["segment"] == "Enterprise"
    assert report["blocker_themes"][0]["theme"] == "Onboarding Flow"
    assert report["unowned_severe_feedback"][0]["account"] == "Acme"
    assert report["recommended_actions"][0] == "Escalate blocker theme 'Onboarding Flow' with 1 blocker record(s)."

    markdown = render_beta_feedback_theme_markdown(report)
    assert "## Summary" in markdown
    assert "- Feedback records: 3" in markdown
    assert "## Themes" in markdown
    assert "| Onboarding Flow | 2 | 1 | 1 | Enterprise, SMB | mixed |" in markdown
    assert json.loads(render_beta_feedback_theme_json(report))["kind"] == KIND


def test_beta_feedback_theme_report_empty_input_returns_zero_counts() -> None:
    report = build_beta_feedback_theme_report([])

    assert report["summary"]["feedback_count"] == 0
    assert report["summary"]["theme_count"] == 0
    assert report["summary"]["segment_count"] == 0
    assert report["theme_rows"] == []
    assert report["segment_breakdown"] == []
    assert report["blocker_themes"] == []
    assert report["unowned_severe_feedback"] == []
    assert report["recommended_actions"] == []
    assert "No beta feedback records were supplied." in render_beta_feedback_theme_markdown(report)
