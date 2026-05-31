from __future__ import annotations

from max.spec.adapter_contract_compliance_plan import generate_adapter_contract_compliance_plan


def test_adapter_contract_compliance_plan_reports_statuses_and_remediation() -> None:
    plan = generate_adapter_contract_compliance_plan(
        [{"name": "none", "methods": []}, {"name": "partial", "methods": ["fetch"]}, {"name": "ok", "methods": ["fetch", "normalize"], "capabilities": ["retry"], "test_evidence": ["pytest"]}],
        {"required_methods": ["fetch", "normalize"], "required_capabilities": ["retry"], "optional_capabilities": ["circuit_breaker"]},
    )

    assert [row["status"] for row in plan["adapters"]] == ["noncompliant", "partial", "compliant"]
    ok = next(row for row in plan["adapters"] if row["adapter"] == "ok")
    assert ok["missing_optional_capabilities"] == ["circuit_breaker"]
    assert plan["summary"] == {"adapter_count": 3, "compliant_count": 1, "partial_count": 1, "noncompliant_count": 1}
    assert plan["remediation_steps"][0]["adapter"] == "none"
