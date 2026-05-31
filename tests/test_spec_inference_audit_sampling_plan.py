from __future__ import annotations

from max.spec.inference_audit_sampling_plan import generate_inference_audit_sampling_plan


def test_inference_audit_sampling_high_risk_priority_and_sections() -> None:
    plan = generate_inference_audit_sampling_plan({"metadata": {"inference_audit_sampling": {"categories": [{"category": "general"}, {"category": "privacy", "risk": "high"}], "privacy_filters": ["redact pii"]}}})
    assert plan["sampling_strategy"][0]["name"] == "privacy"
    assert plan["reviewer_workflow"] and plan["defect_taxonomy"] and plan["escalation_thresholds"] and plan["reporting_cadence"]


def test_inference_audit_sampling_flags_missing_privacy_filters() -> None:
    plan = generate_inference_audit_sampling_plan({"metadata": {"inference_audit_sampling": {"sampling_categories": [{"name": "safety", "risk": "high"}]}}})
    assert [flag["name"] for flag in plan["risk_flags"]] == ["safety", "missing privacy filters"]


def test_inference_audit_sampling_deterministic_for_unordered_categories() -> None:
    payload = {"metadata": {"inference_audit_sampling": {"categories": [{"category": "b"}, {"category": "a"}]}}}
    assert generate_inference_audit_sampling_plan(payload) == generate_inference_audit_sampling_plan(payload)
