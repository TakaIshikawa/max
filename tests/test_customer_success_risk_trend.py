from __future__ import annotations

import json

from max.exports.customer_success_risk_trend import (
    KIND,
    SCHEMA_VERSION,
    build_customer_success_risk_trend_report,
    render_customer_success_risk_trend_json,
    render_customer_success_risk_trend_markdown,
)


def test_customer_success_risk_trend_normalizes_sorts_and_renders() -> None:
    report = build_customer_success_risk_trend_report(
        [
            {"name": "BetaCo", "date": "2026-05-01", "score": "40", "risk_level": "medium", "reason": "Low adoption"},
            {"account": "Acme", "observed_at": "2026-05-01", "risk_score": 30, "status": "low", "driver": "Sponsor gap"},
            {"account_id": "Acme", "observed_at": "2026-05-15", "risk_score": 80, "status": "high", "driver": "Sponsor gap; Usage drop", "evidence": ["qbr"]},
            {"account": "BetaCo", "observed_at": "2026-05-15", "score": 20, "status": "healthy", "drivers": ["Low adoption"]},
        ]
    )

    assert report == build_customer_success_risk_trend_report(
        [
            {"name": "BetaCo", "date": "2026-05-01", "score": "40", "risk_level": "medium", "reason": "Low adoption"},
            {"account": "Acme", "observed_at": "2026-05-01", "risk_score": 30, "status": "low", "driver": "Sponsor gap"},
            {"account_id": "Acme", "observed_at": "2026-05-15", "risk_score": 80, "status": "high", "driver": "Sponsor gap; Usage drop", "evidence": ["qbr"]},
            {"account": "BetaCo", "observed_at": "2026-05-15", "score": 20, "status": "healthy", "drivers": ["Low adoption"]},
        ]
    )
    assert json.loads(json.dumps(report)) == report
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert [row["account"] for row in report["latest_accounts"]] == ["Acme", "BetaCo"]
    assert report["latest_accounts"][0]["risk_delta"] == 50.0
    assert report["movement_counts"] == {"worsened": 1, "improved": 1, "unchanged": 0, "new": 0}
    assert [row["account"] for row in report["top_worsening_accounts"]] == ["Acme"]
    assert report["top_risk_drivers"][0] == {"driver": "Low adoption", "count": 2}

    markdown = render_customer_success_risk_trend_markdown(report)
    assert "## Summary" in markdown
    assert "## Worsening Accounts" in markdown
    assert "- Acme: +50.0 to 80.0" in markdown
    assert json.loads(render_customer_success_risk_trend_json(report))["kind"] == KIND


def test_customer_success_risk_trend_empty_input_returns_zero_counts() -> None:
    report = build_customer_success_risk_trend_report([])

    assert report["summary"]["account_count"] == 0
    assert report["summary"]["snapshot_count"] == 0
    assert report["summary"]["average_latest_risk_score"] == 0.0
    assert report["movement_counts"] == {"worsened": 0, "improved": 0, "unchanged": 0, "new": 0}
    assert report["latest_accounts"] == []
    assert "No customer success risk snapshots were supplied." in render_customer_success_risk_trend_markdown(report)
