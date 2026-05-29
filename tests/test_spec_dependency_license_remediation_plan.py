from __future__ import annotations

from max.spec import generate_dependency_license_remediation_plan


def test_dependency_license_remediation_plan_outputs_sections() -> None:
    plan = generate_dependency_license_remediation_plan({"metadata": {"dependency_license_remediation": {"severity": "high", "dependencies": ["lib-a"], "license_findings": ["GPL usage"], "owners": ["platform"]}}})

    assert plan["summary"]["severity"] == "high"
    assert plan["dependency_inventory"][0]["name"] == "lib-a"
    assert plan["license_findings"][0]["name"] == "GPL usage"
    assert plan["owner_assignments"][0]["name"] == "platform"


def test_dependency_license_remediation_plan_sparse_defaults() -> None:
    plan = generate_dependency_license_remediation_plan({})

    assert plan["summary"]["severity"] == "unknown"
    assert plan["validation"]
    assert plan["legal_signoff"]
