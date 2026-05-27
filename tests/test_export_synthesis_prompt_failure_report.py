from __future__ import annotations

from max.exports import generate_synthesis_prompt_failure_report


def test_synthesis_prompt_failure_report_groups_failed_attempts_only() -> None:
    report = generate_synthesis_prompt_failure_report(
        [
            {"profile": "p", "stage": "draft", "template_id": "t1", "error_class": "Timeout", "status": "failed"},
            {"profile": "p", "stage": "draft", "template_id": "t1", "error_class": "Timeout", "status": "error", "retry_exhausted": True},
            {"profile": "p", "stage": "draft", "template_id": "t1", "error_class": "Timeout", "status": "succeeded"},
        ]
    )

    assert report["summary"]["failed_attempt_count"] == 2
    assert report["summary"]["retry_exhausted_count"] == 1
    assert report["failures"][0]["failed_attempts"] == 2
    assert report["failures"][0]["severity"] == "critical"

