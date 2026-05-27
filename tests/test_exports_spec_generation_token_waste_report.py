from __future__ import annotations

from max.exports import build_spec_generation_token_waste_report


def test_spec_generation_token_waste_report_handles_empty_input() -> None:
    report = build_spec_generation_token_waste_report([])

    assert report["summary"]["attempt_count"] == 0
    assert report["summary"]["waste_ratio"] == 0.0
    assert report["rows"] == []


def test_spec_generation_token_waste_report_aggregates_retries_and_failures() -> None:
    report = build_spec_generation_token_waste_report(
        [
            {"profile": "enterprise", "spec_type": "prd", "model": "gpt-a", "status": "accepted", "total_tokens": 100},
            {"profile": "enterprise", "spec_type": "prd", "model": "gpt-a", "status": "failed", "total_tokens": 80, "failure_reason": "validation"},
            {"profile": "enterprise", "spec_type": "prd", "model": "gpt-a", "status": "accepted", "total_tokens": 20, "retried": True},
            {"profile": "self-serve", "spec_type": "brief", "model": "gpt-b", "status": "accepted", "total_tokens": 50},
        ]
    )

    first = report["rows"][0]
    assert first["profile"] == "enterprise"
    assert first["total_tokens"] == 200
    assert first["accepted_tokens"] == 100
    assert first["failed_tokens"] == 80
    assert first["retried_tokens"] == 20
    assert first["wasted_tokens"] == 100
    assert first["waste_ratio"] == 0.5
    assert first["severity"] == "high"
    assert first["failure_reasons"] == [{"reason": "validation", "count": 1}]


def test_spec_generation_token_waste_report_severity_thresholds_are_deterministic() -> None:
    report = build_spec_generation_token_waste_report(
        [
            {"profile": "p4", "spec_type": "s", "model": "m", "status": "accepted", "total_tokens": 25},
            {"profile": "p4", "spec_type": "s", "model": "m", "status": "failed", "total_tokens": 75},
            {"profile": "p3", "spec_type": "s", "model": "m", "status": "accepted", "total_tokens": 50},
            {"profile": "p3", "spec_type": "s", "model": "m", "status": "failed", "total_tokens": 50},
            {"profile": "p2", "spec_type": "s", "model": "m", "status": "accepted", "total_tokens": 75},
            {"profile": "p2", "spec_type": "s", "model": "m", "status": "failed", "total_tokens": 25},
            {"profile": "p1", "spec_type": "s", "model": "m", "status": "accepted", "total_tokens": 80},
            {"profile": "p1", "spec_type": "s", "model": "m", "status": "failed", "total_tokens": 20},
        ]
    )

    assert [(row["profile"], row["severity"]) for row in report["rows"]] == [
        ("p4", "critical"),
        ("p3", "high"),
        ("p2", "medium"),
        ("p1", "low"),
    ]
