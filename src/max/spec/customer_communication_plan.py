"""Generate deterministic customer communication plans for launches and changes."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, evidence_references, string_list


SCHEMA_VERSION = "max-customer-communication-plan/v1"
KIND = "max.customer_communication_plan"


def generate_customer_communication_plan(spec_like: Any) -> dict[str, Any]:
    """Return stable customer communication planning data."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    project = _section(spec, "project")
    communication = _section(spec, "communication")
    execution = _section(spec, "execution")
    metadata = _section(spec, "metadata")
    risks = string_list(execution.get("risks") or metadata.get("risks"))
    risk_level = _risk_level(risks, communication.get("change_type") or metadata.get("change_type"))
    cadence = "high-touch" if risk_level == "high" else "standard"

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "title": _first(project.get("title"), spec.get("title"), "Unknown"),
            "change_type": _first(communication.get("change_type"), metadata.get("change_type"), "launch"),
            "risk_level": risk_level,
            "communication_cadence": cadence,
        },
        "audiences": _items(communication.get("audiences") or project.get("target_users")),
        "message_themes": _items(communication.get("message_themes") or ["value", "timing", "support path"]),
        "channels": _items(communication.get("channels") or ["email", "in-app", "support enablement"]),
        "timing": _timing(cadence),
        "owner_roles": _items(communication.get("owner_roles") or ["product owner", "customer success", "support lead"]),
        "approvals": _items(communication.get("approvals") or ["product", "legal", "support"]),
        "escalation_paths": _items(communication.get("escalation_paths") or metadata.get("escalation_paths")),
        "evidence": _evidence(spec, metadata),
    }


def _timing(cadence: str) -> list[dict[str, str]]:
    if cadence == "high-touch":
        return [
            {"milestone": "T-14 days", "action": "announce change and support path"},
            {"milestone": "T-3 days", "action": "send reminder with migration or launch checklist"},
            {"milestone": "T+1 day", "action": "confirm status and collect customer-impact signals"},
        ]
    return [
        {"milestone": "T-7 days", "action": "announce launch or operational change"},
        {"milestone": "T+1 day", "action": "share confirmation and support path"},
    ]


def _risk_level(risks: list[str], change_type: Any) -> str:
    text = " ".join(risks + [compact(change_type)]).lower()
    if any(term in text for term in ("migration", "customer-impacting", "downtime", "breaking", "high-risk", "data")):
        return "high"
    if risks:
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
