"""Generate deterministic access review plans for TactSpecs."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, evidence_references, string_list


SCHEMA_VERSION = "max-access-review-plan/v1"
KIND = "max.access_review_plan"


def generate_access_review_plan(spec_like: Any) -> dict[str, Any]:
    """Return a stable access review plan with safe defaults."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    project = _section(spec, "project")
    access = _section(spec, "access")
    metadata = _section(spec, "metadata")
    systems = _items(access.get("systems") or metadata.get("systems_in_scope") or spec.get("systems"))
    roles = _roles(access.get("privileged_roles") or metadata.get("privileged_roles") or spec.get("privileged_roles"))
    sensitive = _is_sensitive(access.get("data_sensitivity") or metadata.get("data_sensitivity") or spec.get("data_sensitivity"))
    privileged = any(role.get("privileged") for role in roles)
    cadence = _cadence(sensitive, privileged, access.get("review_cadence") or metadata.get("review_cadence"))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "title": _first(project.get("title"), spec.get("title"), "Unknown"),
            "review_cadence": cadence,
            "sensitive_data": sensitive,
            "privileged_access": privileged,
        },
        "privileged_roles": roles,
        "systems_in_scope": systems,
        "approvers": _items(access.get("approvers") or metadata.get("approvers")),
        "evidence_requirements": _items(
            access.get("evidence_requirements")
            or ["current user export", "manager approval", "exception register"]
        ),
        "exception_handling": {
            "policy": _first(access.get("exception_policy"), metadata.get("exception_policy"), "Document owner, expiry, and compensating control."),
            "maximum_age_days": 30 if sensitive or privileged else 90,
        },
        "revocation_actions": _items(
            access.get("revocation_actions")
            or ["disable stale account", "remove privileged role", "record completion evidence"]
        ),
        "evidence": _evidence(spec, metadata),
    }


def _roles(value: Any) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else []
    roles: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            name = _first(item.get("name"), item.get("role"), "Unknown")
            privileged = bool(item.get("privileged")) or "admin" in name.lower() or "owner" in name.lower()
        else:
            name = compact(item) or "Unknown"
            privileged = any(term in name.lower() for term in ("admin", "owner", "privileged", "root"))
        roles.append({"name": name, "privileged": privileged})
    if not roles:
        roles.append({"name": "Unknown", "privileged": False})
    return sorted(roles, key=lambda role: role["name"].casefold())


def _cadence(sensitive: bool, privileged: bool, requested: Any) -> str:
    requested_text = compact(requested)
    if sensitive or privileged:
        return "monthly"
    return requested_text or "quarterly"


def _is_sensitive(value: Any) -> bool:
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
