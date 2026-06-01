from __future__ import annotations

from max.spec.customer_environment_isolation_review_plan import generate_customer_environment_isolation_review_plan


def test_customer_environment_isolation_review_plan_groups_shared_dependency_findings() -> None:
    plan = generate_customer_environment_isolation_review_plan(_spec())

    assert [item["name"] for item in plan["environment_reviews"]] == ["enterprise-a", "enterprise-b"]
    assert [item["name"] for item in plan["shared_dependency_findings"]] == ["redis cache", "shared queue"]
    assert all("environment" in item and "shared_dependency" in item for item in plan["findings"])


def test_failed_isolation_evidence_creates_remediation_actions_and_gates() -> None:
    plan = generate_customer_environment_isolation_review_plan(_spec())

    assert any(item["status"] == "failed" for item in plan["findings"])
    assert plan["remediation_actions"]
    assert all(item["gate_required"] is True for item in plan["remediation_actions"])
    assert all(item["status"] == "blocked" for item in plan["remediation_gates"])


def test_missing_test_evidence_creates_remediation_gate() -> None:
    spec = _spec()
    spec["metadata"]["customer_environment_isolation_review"]["test_evidence"] = [
        {"name": "tenant boundary probe", "environment": "enterprise-a", "status": "missing"}
    ]

    plan = generate_customer_environment_isolation_review_plan(spec)

    missing = [item for item in plan["findings"] if item["status"] == "missing"]
    assert missing
    assert any(item["severity"] == "medium" for item in plan["remediation_gates"])


def test_high_severity_findings_are_ordered_first() -> None:
    plan = generate_customer_environment_isolation_review_plan(_spec())

    severities = [item["severity"] for item in plan["findings"]]
    assert severities[0] == "high"
    assert severities.index("high") < severities.index("medium")


def _spec() -> dict:
    return {
        "metadata": {
            "customer_environment_isolation_review": {
                "environments": ["enterprise-b", "enterprise-a"],
                "isolation_controls": ["tenant scoped tokens", "network policies"],
                "shared_dependencies": ["shared queue", "redis cache"],
                "data_boundaries": ["tenant id partition", "per-customer export bucket"],
                "test_evidence": [
                    {"name": "cache probe", "environment": "enterprise-b", "status": "passed"},
                    {"name": "queue probe", "environment": "enterprise-a", "status": "failed", "owner": "qa lead"},
                ],
                "findings": [
                    {"name": "shared queue fallback", "environment": "enterprise-b", "shared_dependency": "shared queue", "severity": "medium"},
                    {"name": "redis namespace leak", "environment": "enterprise-a", "shared_dependency": "redis cache", "severity": "high"},
                ],
            }
        }
    }
