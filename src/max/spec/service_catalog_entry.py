"""Generate deterministic service catalog entries for buildable units or TactSpecs."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, evidence_references, stack_label, string_list


SCHEMA_VERSION = "max-service-catalog-entry/v1"
KIND = "max.service_catalog_entry"


def generate_service_catalog_entry(item: Any) -> dict[str, Any]:
    """Turn a buildable unit or spec-like dict into a stable service catalog entry."""
    data = _as_dict(item)
    metadata = _as_dict(data.get("metadata"))
    spec = data if any(key in data for key in ("source", "project", "solution", "execution", "evidence")) else metadata
    source = _as_dict(spec.get("source"))
    project = _as_dict(spec.get("project"))
    solution = _as_dict(spec.get("solution"))
    execution = _as_dict(spec.get("execution"))
    operations = _as_dict(spec.get("operations") or metadata.get("operations"))
    stack = _as_dict(solution.get("suggested_stack") or metadata.get("runtime"))

    title = _first(data.get("title"), project.get("title"), source.get("idea_id"), "Unknown")
    idea_id = _first(data.get("id"), source.get("idea_id"), "Unknown")
    owners = _sorted_unique(metadata.get("owners") or project.get("owners"))
    dependencies = _sorted_unique(
        metadata.get("dependencies")
        or solution.get("dependencies")
        or execution.get("dependencies")
        or _stack_dependencies(stack)
    )
    evidence = _evidence(spec, metadata)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "idea_id": idea_id,
            "system": _first(source.get("system"), "max"),
            "type": _first(source.get("type"), data.get("type"), "Unknown"),
            "domain": _first(source.get("domain"), data.get("domain"), "Unknown"),
            "category": _first(source.get("category"), data.get("category"), "Unknown"),
        },
        "ownership": {
            "service_owner": _first(metadata.get("service_owner"), project.get("buyer"), data.get("buyer"), "Unknown"),
            "technical_owner": _first(metadata.get("technical_owner"), solution.get("technical_owner"), "Unknown"),
            "business_owner": _first(metadata.get("business_owner"), project.get("buyer"), data.get("buyer"), "Unknown"),
            "support_group": _first(metadata.get("support_group"), operations.get("support_group"), "Unknown"),
            "owners": owners,
        },
        "purpose": {
            "name": title,
            "summary": _first(project.get("summary"), data.get("one_liner"), data.get("summary"), "Unknown"),
            "workflow_context": _first(project.get("workflow_context"), data.get("workflow_context"), "Unknown"),
            "target_users": _first(project.get("specific_user"), project.get("target_users"), data.get("target_users"), "Unknown"),
        },
        "runtime": {
            "environment": _first(metadata.get("environment"), operations.get("environment"), "Unknown"),
            "stack": stack_label(stack) or "Unknown",
            "runtime_summary": _first(solution.get("technical_approach"), solution.get("approach"), data.get("tech_approach"), "Unknown"),
        },
        "dependencies": dependencies,
        "data": {
            "classification": _classification(metadata, spec),
            "data_stores": _sorted_unique(metadata.get("data_stores") or solution.get("data_stores")),
            "retention_reference": _first(metadata.get("retention_reference"), spec.get("retention_reference"), "Unknown"),
        },
        "operations": {
            "contacts": _sorted_unique(metadata.get("operational_contacts") or operations.get("contacts")),
            "slo_references": _sorted_unique(metadata.get("slo_references") or operations.get("slo_references")),
            "runbook": _first(metadata.get("runbook"), operations.get("runbook"), "Unknown"),
        },
        "evidence": evidence,
    }


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    result: dict[str, Any] = {}
    for name in (
        "id",
        "title",
        "metadata",
        "type",
        "domain",
        "category",
        "buyer",
        "target_users",
        "workflow_context",
        "one_liner",
        "summary",
        "tech_approach",
    ):
        if hasattr(value, name):
            result[name] = getattr(value, name)
    return result


def _classification(metadata: dict[str, Any], spec: dict[str, Any]) -> str:
    value = _first(metadata.get("data_classification"), spec.get("data_classification"), metadata.get("classification"), "")
    text = value.lower()
    if any(term in text for term in ("restricted", "confidential", "pii", "phi", "pci")):
        return value
    if text:
        return value
    joined = " ".join(string_list(metadata.get("data_types")) + string_list(spec.get("data_types"))).lower()
    if any(term in joined for term in ("pii", "personal", "phi", "pci")):
        return "Restricted"
    return "Unknown"


def _evidence(spec: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    refs = [item["reference"] for item in evidence_references(spec)]
    refs.extend(string_list(metadata.get("evidence_links") or metadata.get("evidence")))
    return _sorted_unique(refs)


def _stack_dependencies(stack: dict[str, Any]) -> list[str]:
    return [f"{compact(key)}:{compact(value)}" for key, value in stack.items() if compact(key) and compact(value)]


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
