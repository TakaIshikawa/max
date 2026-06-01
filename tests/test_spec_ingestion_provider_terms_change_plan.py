from __future__ import annotations

from max.spec import generate_ingestion_provider_terms_change_plan


def test_ingestion_provider_terms_change_plan_captures_risk_and_mitigations() -> None:
    plan = generate_ingestion_provider_terms_change_plan({"provider": "Example API", "effective_date": "2026-01-01", "affected_adapters": ["aws"], "retention_changes": ["30 days"], "rate_limit_changes": ["100/min"], "allowed_uses": ["news"]}, as_of="2026-06-01")

    assert plan["schema_version"] == "max.spec.ingestion_provider_terms_change_plan.v1"
    assert plan["kind"] == "max.spec.ingestion_provider_terms_change_plan"
    assert plan["provider"] == "Example API"
    assert plan["affected_adapters"][0]["adapter"] == "aws"
    assert "effective_date_in_past" in plan["validation_issues"]
    assert "missing_compliance_owner" in plan["validation_issues"]
    assert {step["area"] for step in plan["mitigation_steps"]} == {"retention", "attribution", "rate_limit"}
