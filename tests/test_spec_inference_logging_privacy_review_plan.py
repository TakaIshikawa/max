from __future__ import annotations

import json

from max.spec.inference_logging_privacy_review_plan import generate_inference_logging_privacy_review_plan


def test_inference_logging_privacy_review_plan_classifies_logged_fields_and_controls() -> None:
    plan = generate_inference_logging_privacy_review_plan(
        {
            "evidence": {"signal_ids": ["log-privacy"]},
            "metadata": {
                "inference_logging_privacy_review": {
                    "logged_fields": [
                        {"field": "tenant_id", "classification": "confidential", "redaction": "hash"},
                        {"field": "redacted_response_summary", "redaction": "applied"},
                    ],
                    "redaction_controls": ["hash tenant identifiers before persistence"],
                    "encryption": ["managed-key encrypted log store"],
                    "retention": [{"duration": "14 days"}],
                    "sampling_access": [{"role": "privacy reviewer", "sampling_rate": "1%"}],
                    "incident_triggers": ["redaction failure on sampled prompt"],
                    "approval_gates": ["privacy and security approval before enabling response summaries"],
                }
            },
        }
    )

    assert plan["schema_version"] == "max.spec.inference_logging_privacy_review_plan.v1"
    assert [field["name"] for field in plan["logged_fields"]] == ["redacted_response_summary", "tenant_id"]
    assert plan["logged_fields"][0]["classification"] == "sensitive"
    assert plan["logged_fields"][1]["classification"] == "confidential"
    assert plan["retention_period"][0]["duration"] == "14 days"
    assert plan["sampling_access"][0]["sampling_rate"] == "1%"
    assert plan["risk_flags"][0]["severity"] == "low"
    assert plan["evidence_references"][0]["reference"] == "signal:log-privacy"
    assert json.loads(json.dumps(plan)) == plan


def test_inference_logging_privacy_review_plan_defaults_required_sections() -> None:
    plan = generate_inference_logging_privacy_review_plan({})

    assert plan["logged_fields"][0]["name"] == "redacted_prompt_summary"
    assert plan["logged_fields"][0]["classification"] == "sensitive"
    assert set(plan) >= {
        "logged_fields",
        "redaction_controls",
        "encryption_controls",
        "retention_period",
        "sampling_access",
        "access_monitoring",
        "incident_triggers",
        "approval_gates",
    }


def test_inference_logging_privacy_review_plan_flags_unredacted_raw_prompt_or_response() -> None:
    plan = generate_inference_logging_privacy_review_plan(
        {
            "metadata": {
                "inference_logging_privacy_review": {
                    "fields": [
                        {"field": "raw_prompt", "redaction": "none"},
                        {"field": "raw_response", "redaction": "disabled"},
                    ]
                }
            }
        }
    )

    assert [flag["severity"] for flag in plan["risk_flags"]] == ["high", "high"]
    assert plan["summary"]["high_risk_count"] == 2
    assert "raw prompt or response" in plan["risk_flags"][0]["description"].lower()
