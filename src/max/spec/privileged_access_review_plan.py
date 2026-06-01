"""Generate deterministic privileged access review plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.privileged_access_review_plan.v1"
KIND = "max.spec.privileged_access_review_plan"


def generate_privileged_access_review_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    system = _required(hints, "system_name", "system name")
    roles = _required_list(hints.get("privileged_roles"), "privileged roles")
    reviewers = _required_list(hints.get("reviewers"), "reviewers")
    window = _required(hints, "review_window", "review window")
    evidence_sources = _list(hints.get("evidence_sources"), ["IAM export", "admin audit log"])
    exception_policy = compact(hints.get("exception_policy")) or "document and approve temporary access exceptions"
    revocation_owners = _list(hints.get("revocation_owners"), reviewers)
    overdue = "overdue" in window.casefold() or "past due" in window.casefold()
    refs = [item["id"] for item in ctx["evidence_references"]]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, system_name=system, role_count=len(roles), review_window=window, overdue=overdue),
        "evidence_collection": [_row("PAE", i, source, reviewers[0], f"Collect privileged access evidence from {source}.", refs) for i, source in enumerate(evidence_sources, 1)],
        "role_attestations": [_row("PAR", i, role, reviewers[(i - 1) % len(reviewers)], f"Attest privileged role {role} for {system}.", refs, status="overdue" if overdue else "pending") for i, role in enumerate(roles, 1)],
        "exception_handling": [_row("PAX", 1, "Exception policy review", reviewers[0], exception_policy, refs)],
        "revocation_tasks": [_row("PAV", i, role, revocation_owners[(i - 1) % len(revocation_owners)], f"Revoke or justify inappropriate access for {role}.", refs) for i, role in enumerate(roles, 1)],
        "completion_criteria": [_row("PAC", 1, "Review completion", reviewers[0], "Complete when all roles are attested, exceptions approved, and revocations evidenced.", refs)],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    value = metadata.get("privileged_access_review")
    return value if isinstance(value, dict) else {}


def _required(hints: dict[str, Any], key: str, label: str) -> str:
    value = compact(hints.get(key))
    if not value:
        raise ValueError(f"privileged_access_review requires {label}")
    return value


def _required_list(value: Any, label: str) -> list[str]:
    values = _list(value, [])
    if not values:
        raise ValueError(f"privileged_access_review requires {label}")
    return values


def _list(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(item for item in values if item), key=str.casefold) or fallback


def _row(prefix: str, index: int, name: str, owner: str, description: str, refs: list[str], **extra: Any) -> dict[str, Any]:
    data = {"id": f"{prefix}{index}", "name": name, "owner": owner, "description": description, "evidence_reference_ids": refs}
    data.update({key: value for key, value in extra.items() if value not in ("", None)})
    return data
