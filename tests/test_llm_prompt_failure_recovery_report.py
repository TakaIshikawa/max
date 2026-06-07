from __future__ import annotations

from max.exports import generate_llm_prompt_failure_recovery_report


def test_llm_prompt_failure_recovery_groups_by_stage_and_prompt_version() -> None:
    report = generate_llm_prompt_failure_recovery_report(
        [
            {"stage": "synthesis", "prompt_version": "v1", "retry_count": 1, "recovery_outcome": "recovered"},
            {"stage": "synthesis", "prompt_version": "v1", "retry_count": 1, "recovery_outcome": "failed"},
            {"stage": "publish", "prompt_version": "v2", "failure_count": 4, "retry_count": 4, "recovered_count": 4},
        ],
        minimum_recovery_rate=0.75,
    )

    assert report["rows"][0]["stage"] == "synthesis"
    assert report["rows"][0]["failure_count"] == 2
    assert report["rows"][0]["retry_count"] == 2
    assert report["rows"][0]["recovered_count"] == 1
    assert report["rows"][0]["unrecovered_count"] == 1
    assert report["rows"][0]["recovery_rate"] == 0.5
    assert report["rows"][0]["status"] == "below_target"
    assert report["rows"][1]["status"] == "healthy"


def test_llm_prompt_failure_recovery_empty() -> None:
    assert generate_llm_prompt_failure_recovery_report([])["summary"]["group_count"] == 0
