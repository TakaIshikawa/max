from __future__ import annotations

from max.spec.model_output_retention_plan import generate_model_output_retention_plan


def test_model_output_retention_renders_rules_and_controls() -> None:
    plan = generate_model_output_retention_plan({"metadata": {"model_output_retention": {"retention_rules": [{"output_class": "summary", "retention_period": "30d"}]}}})
    assert plan["retention_rules"][0]["name"] == "summary"
    assert plan["deletion_triggers"] and plan["legal_holds"] and plan["audit_evidence"] and plan["exception_handling"]


def test_model_output_retention_sensitive_requires_review() -> None:
    plan = generate_model_output_retention_plan({"metadata": {"model_output_retention": {"rules": [{"name": "customer pii output", "retention_period": "7d"}]}}})
    assert plan["review_actions"][0]["severity"] == "high"
    assert "shorter review cadence" in plan["review_actions"][0]["description"]


def test_model_output_retention_empty_rules_bootstrap_gap_checklist() -> None:
    plan = generate_model_output_retention_plan({})
    assert plan["retention_rules"][0]["retention_period"] == "define before launch"
