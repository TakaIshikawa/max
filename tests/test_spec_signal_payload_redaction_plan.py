from __future__ import annotations

from max.spec.signal_payload_redaction_plan import generate_signal_payload_redaction_plan


def test_critical_sensitive_fields_are_prioritized() -> None:
    plan = generate_signal_payload_redaction_plan({"fields": [{"field": "email", "severity": "low"}, {"field": "password", "severity": "critical"}]})
    assert plan["redaction_actions"][0]["field"] == "password"


def test_output_includes_owner_actions_and_verification() -> None:
    plan = generate_signal_payload_redaction_plan({"fields": [{"field": "token"}]})
    assert plan["owner_assignments"]
    assert plan["verification_gates"]


def test_no_findings_produces_clean_state_plan() -> None:
    plan = generate_signal_payload_redaction_plan({})
    assert plan["summary"]["status"] == "clean"
    assert plan["redaction_actions"][0]["field"] == "none"
