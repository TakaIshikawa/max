from __future__ import annotations

from max.spec.publication_approval_delegation_plan import generate_publication_approval_delegation_plan


def test_missing_or_expired_delegates_are_blocking() -> None:
    plan = generate_publication_approval_delegation_plan({"metadata": {"publication_approval_delegation": {"destinations": [{"destination": "docs"}, {"destination": "blog", "delegate": "a", "expires_at": "2020-01-01"}]}}})
    assert plan["summary"]["blocked_delegation_count"] == 2
    assert all(row["blocking"] for row in plan["delegation_matrix"])


def test_high_risk_destinations_get_escalation_and_audit() -> None:
    plan = generate_publication_approval_delegation_plan({"destinations": [{"destination": "status-page", "delegate": "ops", "risk": "high"}]})
    assert plan["escalation_paths"][0]["destination"] == "status-page"
    assert plan["audit_checks"]


def test_summary_reports_highest_risk_destination() -> None:
    plan = generate_publication_approval_delegation_plan({"destinations": [{"destination": "low", "delegate": "a"}, {"destination": "prod", "high_risk": True}]})
    assert plan["summary"]["highest_risk_destination"] == "prod"
