from __future__ import annotations

import json

from max.exports.trial_conversion_readiness_scorecard import (
    build_trial_conversion_readiness_scorecard,
    render_trial_conversion_readiness_scorecard_json,
    render_trial_conversion_readiness_scorecard_markdown,
)


def test_trial_readiness_orders_low_scores_and_blockers_first() -> None:
    report = build_trial_conversion_readiness_scorecard([
        {
            "account_id": "ready",
            "account_name": "Ready Co",
            "activation": 95,
            "usage_depth": 90,
            "stakeholder_engagement": "strong",
            "owner": "ae",
            "trial_end_date": "2026-07-15",
        },
        {
            "account_id": "blocked",
            "account_name": "Blocked Co",
            "activation": 25,
            "usage_depth": 30,
            "stakeholder_engagement": "weak",
            "blockers": ["security review", "no sponsor"],
            "owner": "csm",
            "trial_end_date": "2026-06-01",
        },
        {
            "account_id": "watch",
            "account_name": "Watch Co",
            "activation": 65,
            "usage_depth": 55,
            "stakeholder_engagement": 60,
            "blockers": "procurement",
            "trial_end_date": "2026-06-15",
        },
    ])

    assert [row["account_id"] for row in report["accounts"]] == ["blocked", "watch", "ready"]
    assert report["accounts"][0]["readiness_band"] == "blocked"
    assert report["accounts"][-1]["readiness_band"] == "ready"
    assert report["summary"]["band_counts"] == {"ready": 1, "watch": 1, "blocked": 1}
    markdown = render_trial_conversion_readiness_scorecard_markdown(report)
    assert markdown.index("| Blocked Co |") < markdown.index("| Ready Co |")
    assert "Resolve no sponsor before conversion ask." in markdown


def test_trial_readiness_merges_duplicate_account_rows() -> None:
    report = build_trial_conversion_readiness_scorecard([
        {
            "account_id": "acct-1",
            "account_name": "Northwind",
            "activation_score": 40,
            "usage_score": 55,
            "stakeholder_score": 35,
            "blockers": "setup incomplete",
            "trial_end_date": "2026-06-20",
        },
        {
            "account_id": "acct-1",
            "account_name": "Northwind",
            "activation_score": 75,
            "usage_score": 60,
            "stakeholder_score": 45,
            "blockers": "pricing; setup incomplete",
            "owner": "growth",
            "trial_end_date": "2026-06-10",
        },
    ])

    assert report["summary"]["account_count"] == 1
    account = report["accounts"][0]
    assert account["activation_score"] == 75
    assert account["owner"] == "growth"
    assert account["trial_end_date"] == "2026-06-10"
    assert account["blockers"] == ["pricing", "setup incomplete"]


def test_trial_readiness_empty_defaults_and_json_renderer() -> None:
    report = build_trial_conversion_readiness_scorecard([])

    assert report["summary"]["account_count"] == 0
    markdown = render_trial_conversion_readiness_scorecard_markdown(report)
    assert "No trial accounts supplied for readiness scoring." in markdown
    assert "Capture trial activation" in markdown
    assert json.loads(render_trial_conversion_readiness_scorecard_json(report))["accounts"] == []


def test_trial_readiness_preserves_zero_scores() -> None:
    report = build_trial_conversion_readiness_scorecard([
        {"account_id": "zero", "activation_score": 0, "usage_score": 0, "stakeholder_score": 0}
    ])

    assert report["accounts"][0]["activation_score"] == 0
    assert report["accounts"][0]["usage_depth_score"] == 0
    assert report["accounts"][0]["stakeholder_engagement_score"] == 0
    assert report["accounts"][0]["readiness_score"] == 10
