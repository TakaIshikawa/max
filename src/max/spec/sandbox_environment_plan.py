"""Generate deterministic sandbox environment plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, evidence_references, string_list


SCHEMA_VERSION = "max-sandbox-environment-plan/v1"
KIND = "max.sandbox_environment_plan"


def generate_sandbox_environment_plan(spec_like: Any) -> dict[str, Any]:
    """Return stable sandbox or staging environment provisioning guidance."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    project = _section(spec, "project")
    sandbox = _section(spec, "sandbox")
    metadata = _section(spec, "metadata")
    sensitive = _sensitive(sandbox.get("data_sensitivity") or metadata.get("data_sensitivity") or spec.get("data_sensitivity"))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "title": _first(project.get("title"), spec.get("title"), "Unknown"),
            "sensitive_data": sensitive,
            "data_policy": "sanitized_or_synthetic_required" if sensitive else "non_production_allowed",
        },
        "environment_purpose": _first(sandbox.get("purpose"), project.get("workflow_context"), "Unknown"),
        "data_seeding_rules": _items(sandbox.get("data_seeding_rules") or _default_seed_rules(sensitive)),
        "access_controls": _items(sandbox.get("access_controls") or ["least privilege", "time-bound access", "audit logging"]),
        "integration_stubs": _items(sandbox.get("integration_stubs") or metadata.get("integration_stubs")),
        "reset_cadence": _first(sandbox.get("reset_cadence"), "weekly"),
        "cost_guardrails": _items(sandbox.get("cost_guardrails") or ["auto-shutdown idle resources", "monthly budget alert"]),
        "promotion_criteria": _items(sandbox.get("promotion_criteria") or ["tests pass", "data policy verified", "owner signoff"]),
        "evidence": _evidence(spec, metadata),
    }


def _default_seed_rules(sensitive: bool) -> list[str]:
    if sensitive:
        return ["use synthetic records", "mask production identifiers", "block raw production exports"]
    return ["use representative non-production fixtures"]


def _sensitive(value: Any) -> bool:
    return any(term in compact(value).lower() for term in ("pii", "phi", "pci", "restricted", "regulated", "confidential"))


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
