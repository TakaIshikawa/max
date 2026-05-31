"""Generate adapter contract compliance plans."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


def generate_adapter_contract_compliance_plan(adapter_inventory: Iterable[Mapping[str, Any]], contract_requirements: Mapping[str, Any]) -> dict[str, Any]:
    required = set(_list(contract_requirements.get("required_methods"))) | set(_list(contract_requirements.get("required_capabilities")))
    optional = set(_list(contract_requirements.get("optional_capabilities")))
    adapters = []
    remediation = []
    for adapter in adapter_inventory:
        name = _text(adapter.get("adapter") or adapter.get("name") or adapter.get("id")) or "unknown-adapter"
        capabilities = set(_list(adapter.get("methods"))) | set(_list(adapter.get("capabilities"))) | set(_list(adapter.get("normalized_fields")))
        missing_required = sorted(required - capabilities)
        missing_optional = sorted(optional - capabilities)
        status = "compliant" if not missing_required else ("partial" if capabilities & required else "noncompliant")
        row = {"adapter": name, "status": status, "missing_contract_items": missing_required, "missing_optional_capabilities": missing_optional, "test_evidence": _list(adapter.get("test_evidence"))}
        adapters.append(row)
        for item in missing_required:
            remediation.append({"adapter": name, "contract_item": item, "priority": "high" if status == "noncompliant" else "medium", "step": f"Implement and test {item}."})
    adapters.sort(key=lambda row: ({"noncompliant": 0, "partial": 1, "compliant": 2}[row["status"]], row["adapter"]))
    remediation.sort(key=lambda row: (row["adapter"], row["contract_item"]))
    return {"schema_version": "max.adapter_contract_compliance_plan.v1", "kind": "max.adapter_contract_compliance_plan", "summary": {"adapter_count": len(adapters), "compliant_count": sum(1 for row in adapters if row["status"] == "compliant"), "partial_count": sum(1 for row in adapters if row["status"] == "partial"), "noncompliant_count": sum(1 for row in adapters if row["status"] == "noncompliant")}, "adapters": adapters, "required_contract_items": sorted(required), "optional_capabilities": sorted(optional), "remediation_steps": remediation}


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [] if value in (None, "") else [_text(value)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
