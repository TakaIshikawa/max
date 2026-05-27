from __future__ import annotations

import json

from max.exports.inference_prompt_redaction_gap_report import (
    build_inference_prompt_redaction_gap_report,
    render_inference_prompt_redaction_gap_report_json,
)


def test_inference_prompt_redaction_gap_report_groups_gaps_by_provider_model_profile() -> None:
    report = build_inference_prompt_redaction_gap_report(
        [
            {"id": "p1", "provider": "OpenAI", "model": "gpt-4.1", "profile": "prod", "unredacted_sensitive_fields": ["email"]},
            {"id": "p2", "provider": "OpenAI", "model": "gpt-4.1", "profile": "prod", "unredacted_sensitive_fields": ["api_key"]},
            {"id": "p3", "provider": "Anthropic", "model": "claude", "profile": "beta", "redacted_sensitive_fields": ["phone"]},
        ]
    )

    assert report["summary"]["prompt_count"] == 3
    assert report["summary"]["redacted_prompt_count"] == 1
    assert report["summary"]["unredacted_sensitive_field_gap_count"] == 2
    assert report["risk_rows"][0]["provider"] == "OpenAI"
    assert report["risk_rows"][0]["prompt_ids"] == ["p1", "p2"]
    assert report["risk_rows"][0]["unredacted_sensitive_fields"] == ["api_key", "email"]


def test_inference_prompt_redaction_gap_report_ranks_highest_risk_first() -> None:
    report = build_inference_prompt_redaction_gap_report(
        [
            {"id": "low", "provider": "B", "model": "m", "profile": "prod", "unredacted_sensitive_fields": ["email"]},
            {"id": "high", "provider": "A", "model": "m", "profile": "prod", "unredacted_sensitive_fields": ["private_key"]},
            {"id": "mid", "provider": "C", "model": "m", "profile": "prod", "unredacted_sensitive_fields": ["password"]},
        ]
    )

    assert [row["provider"] for row in report["risk_rows"]] == ["A", "C", "B"]
    assert report["summary"]["highest_risk_score"] == 10


def test_inference_prompt_redaction_gap_report_fully_redacted_input_has_zero_gaps() -> None:
    report = build_inference_prompt_redaction_gap_report(
        [{"id": "safe", "provider": "OpenAI", "model": "gpt-4.1", "profile": "prod", "redacted_sensitive_fields": ["email", "token"]}]
    )

    assert report["summary"]["redacted_prompt_count"] == 1
    assert report["summary"]["unredacted_sensitive_field_gap_count"] == 0
    assert report["risk_rows"] == []
    assert report["redaction_gaps"] == []


def test_inference_prompt_redaction_gap_report_missing_fields_are_stable() -> None:
    report = build_inference_prompt_redaction_gap_report([{}])

    assert report["prompts"] == [
        {
            "id": "prompt-1",
            "provider": "unknown",
            "model": "unknown",
            "profile": "default",
            "redaction_status": "unknown",
            "sensitive_fields": [],
            "redacted_sensitive_fields": [],
            "unredacted_sensitive_fields": [],
            "gap_count": 0,
            "risk_score": 0,
        }
    ]


def test_inference_prompt_redaction_gap_report_output_is_deterministic() -> None:
    records = [
        {"id": "b", "provider": "OpenAI", "model": "z", "profile": "prod", "unredacted_sensitive_fields": ["token"]},
        {"id": "a", "provider": "OpenAI", "model": "a", "profile": "prod", "redacted_sensitive_fields": ["email"]},
    ]

    first = render_inference_prompt_redaction_gap_report_json(build_inference_prompt_redaction_gap_report(records))
    second = render_inference_prompt_redaction_gap_report_json(build_inference_prompt_redaction_gap_report(reversed(records)))
    assert first == second


def test_inference_prompt_redaction_gap_report_preserves_metadata() -> None:
    report = build_inference_prompt_redaction_gap_report([], metadata={"source": "audit", "tags": ["privacy"]})

    assert report["metadata"] == {"source": "audit", "tags": ["privacy"]}
    assert (
        json.loads(render_inference_prompt_redaction_gap_report_json(report))["kind"]
        == "max.inference_prompt_redaction_gap_report"
    )
