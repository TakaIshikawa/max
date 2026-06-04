from __future__ import annotations

from max.exports.profile_source_reliability_report import generate_profile_source_reliability_report


def test_groups_by_profile_and_source() -> None:
    report = generate_profile_source_reliability_report([{"profile_id": "p1", "source": "github", "status": "success"}, {"profile_id": "p1", "source": "github", "status": "timeout"}])
    assert report["rows"][0]["profile_id"] == "p1"
    assert report["rows"][0]["source"] == "github"
    assert report["rows"][0]["attempt_count"] == 2
    assert report["rows"][0]["success_rate"] == 0.5


def test_success_rate_is_zero_safe_without_attempts() -> None:
    report = generate_profile_source_reliability_report([{"profile_id": "p1", "source": "rss", "attempts": 0, "successes": 0}])
    assert report["rows"][0]["success_rate"] == 0.0


def test_timeouts_and_circuit_open_escalate_risk() -> None:
    report = generate_profile_source_reliability_report([{"profile_id": "p1", "source": "a", "attempts": 10, "successes": 9}, {"profile_id": "p1", "source": "b", "attempts": 10, "successes": 9, "circuit_open": True}, {"profile_id": "p1", "source": "c", "timeout_count": 1}])
    risks = {row["source"]: row["reliability_risk"] for row in report["rows"]}
    assert risks == {"a": "low", "b": "high", "c": "medium"}
