"""Generate deterministic AI usage policy specs."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, evidence_references, string_list


SCHEMA_VERSION = "max-ai-usage-policy/v1"
KIND = "max.ai_usage_policy"


def generate_ai_usage_policy(spec_like: Any) -> dict[str, Any]:
    """Return a stable AI usage policy with conservative defaults."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    project = _section(spec, "project")
    ai = _section(spec, "ai")
    metadata = _section(spec, "metadata")
    regulated = _strict(ai, metadata, spec)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "title": _first(project.get("title"), spec.get("title"), "Unknown"),
            "control_level": "strict" if regulated else "standard",
            "automated_decisions": _truthy(ai.get("automated_decisions") or metadata.get("automated_decisions")),
        },
        "approved_use_cases": _items(ai.get("approved_use_cases") or metadata.get("approved_use_cases")),
        "prohibited_data": _items(ai.get("prohibited_data") or _default_prohibited(regulated)),
        "human_review": {
            "required": regulated,
            "requirements": _items(ai.get("human_review_requirements") or _default_review(regulated)),
        },
        "logging_audit": _items(ai.get("logging_audit_needs") or ["prompt and response trace", "model version", "review outcome"]),
        "vendor_constraints": _items(ai.get("vendor_constraints") or metadata.get("vendor_constraints") or ["approved vendor list"]),
        "policy_exceptions": {
            "allowed": False if regulated else True,
            "requirements": _items(ai.get("policy_exceptions") or ["named owner", "expiry date", "risk acceptance"]),
        },
        "evidence": _evidence(spec, metadata),
    }


def _strict(ai: dict[str, Any], metadata: dict[str, Any], spec: dict[str, Any]) -> bool:
    text = " ".join(
        string_list(ai.get("data_types"))
        + string_list(metadata.get("data_types"))
        + [compact(ai.get("domain") or metadata.get("domain") or spec.get("domain"))]
    ).lower()
    return _truthy(ai.get("automated_decisions") or metadata.get("automated_decisions")) or any(
        term in text for term in ("pii", "phi", "pci", "regulated", "healthcare", "finance", "legal")
    )


def _default_prohibited(strict: bool) -> list[str]:
    base = ["secrets", "credentials", "unredacted customer data"]
    return base + ["regulated personal data", "automated adverse decisioning"] if strict else base


def _default_review(strict: bool) -> list[str]:
    if strict:
        return ["human approval before customer impact", "bias review", "security review"]
    return ["sampled output review"]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return compact(value).lower() in {"true", "yes", "1", "required"}


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
