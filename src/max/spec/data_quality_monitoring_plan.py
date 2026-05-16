"""Generate deterministic data quality monitoring plans for TactSpecs."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, evidence_references, string_list


SCHEMA_VERSION = "max-data-quality-monitoring-plan/v1"
KIND = "max.data_quality_monitoring_plan"


def generate_data_quality_monitoring_plan(spec_like: Any) -> dict[str, Any]:
    """Return structured data quality monitoring guidance without side effects."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    project = _section(spec, "project")
    metadata = _section(spec, "metadata")
    data = _section(spec, "data")
    operations = _section(spec, "operations")
    datasets = _items(data.get("critical_datasets") or metadata.get("critical_datasets") or spec.get("datasets"))
    sensitivity = _first(data.get("data_sensitivity"), metadata.get("data_sensitivity"), spec.get("data_sensitivity"), "Unknown")
    criticality = _first(data.get("business_criticality"), metadata.get("business_criticality"), spec.get("business_criticality"), "Unknown")
    severity = _severity(criticality, sensitivity)
    dimensions = _sorted_unique(data.get("quality_dimensions") or ["freshness", "completeness", "validity"])

    checks = [
        _check("DQC1", "Freshness", "freshness", "dataset updated within expected window", "high" if severity == "critical" else severity),
        _check("DQC2", "Completeness", "completeness", "required fields are populated", severity),
        _check("DQC3", "Validity", "validity", "records conform to schema and accepted values", severity),
    ]
    for name in datasets:
        checks.append(_check(f"DQC{len(checks) + 1}", f"{name} row volume", "volume", "row volume stays within historical bounds", severity))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "title": _first(project.get("title"), spec.get("title"), "Unknown"),
            "business_criticality": criticality,
            "data_sensitivity": sensitivity,
            "monitoring_priority": severity,
        },
        "datasets": datasets,
        "dimensions": dimensions,
        "checks": checks,
        "thresholds": _thresholds(severity),
        "alerts": {
            "routing": _sorted_unique(operations.get("alert_routing") or metadata.get("alert_routing")),
            "severity": severity,
            "notify_after_minutes": 5 if severity == "critical" else 15 if severity == "high" else 60,
        },
        "remediation": _sorted_unique(operations.get("remediation_playbooks") or metadata.get("remediation_playbooks")),
        "evidence": _evidence(spec, metadata),
    }


def _check(id_: str, name: str, dimension: str, condition: str, severity: str) -> dict[str, str]:
    return {"id": id_, "name": name, "dimension": dimension, "condition": condition, "severity": severity}


def _thresholds(priority: str) -> dict[str, str]:
    if priority == "critical":
        return {"freshness": "15 minutes", "completeness": "99.5%", "validity": "99.5%"}
    if priority == "high":
        return {"freshness": "60 minutes", "completeness": "99%", "validity": "99%"}
    return {"freshness": "24 hours", "completeness": "95%", "validity": "95%"}


def _severity(criticality: str, sensitivity: str) -> str:
    text = f"{criticality} {sensitivity}".lower()
    if any(term in text for term in ("critical", "regulated", "restricted", "pii", "phi", "pci")):
        return "critical"
    if any(term in text for term in ("high", "confidential", "customer")):
        return "high"
    if any(term in text for term in ("medium", "internal")):
        return "medium"
    return "low"


def _section(spec: dict[str, Any], name: str) -> dict[str, Any]:
    value = spec.get(name)
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[str]:
    return _sorted_unique(value) or ["Unknown"]


def _evidence(spec: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    refs = [item["reference"] for item in evidence_references(spec)]
    refs.extend(string_list(metadata.get("evidence_links")))
    return _sorted_unique(refs)


def _sorted_unique(value: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in string_list(value):
        if item not in seen:
            seen.add(item)
            result.append(item)
    return sorted(result, key=str.casefold)


def _first(*values: Any) -> str:
    for value in values:
        text = compact(value)
        if text:
            return text
    return "Unknown"
