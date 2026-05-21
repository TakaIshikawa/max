"""Generate deterministic data access exception review plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.data_access_exception_review_plan.v1"
KIND = "max.spec.data_access_exception_review_plan"


def generate_data_access_exception_review_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "data_access_exception_review")
    exceptions = unique_records(
        _named(hints.get("requesters") or hints.get("exceptions"), ("requester", "dataset")),
        [
            {
                "name": "restricted data access exception",
                "owner": "security_owner",
                "severity": "medium",
                "expiry": "not recorded",
            }
        ],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, exception_count=len(exceptions)),
        "access_exceptions": [_item("DAE", index, item, "security_owner", evidence_ids) for index, item in enumerate(exceptions, start=1)],
        "access_scope": _section(hints, ("datasets", "access_scope", "scope"), "DAS", "data_owner", "Confirm access scope", evidence_ids, ["dataset and permission scope"]),
        "justifications": _section(hints, ("justification", "justifications"), "DAJ", "request_owner", "Validate business justification", evidence_ids, ["access justification"]),
        "compensating_controls": _section(hints, ("compensating_controls", "controls"), "DAC", "security_owner", "Operate compensating control", evidence_ids, ["monitoring and least privilege control"]),
        "approval_gates": _section(hints, ("approvers", "approvals"), "DAA", "approval_owner", "Capture access approval", evidence_ids, ["security and data owner approval"]),
        "expiry_reviews": _section(hints, ("expiry", "expiries", "expiration_reviews"), "DAX", "security_owner", "Review access expiry", evidence_ids, ["access revocation date"]),
        "evidence_references": ctx["evidence_references"],
    }


def _section(hints: dict[str, Any], keys: tuple[str, ...], prefix: str, owner: str, label: str, evidence_ids: list[str], fallback: list[Any]) -> list[dict[str, Any]]:
    value = next((hints[key] for key in keys if key in hints), None)
    return [_item(prefix, index, item, owner, evidence_ids, label) for index, item in enumerate(unique_records(value, fallback), start=1)]


def _item(prefix: str, index: int, item: dict[str, Any], owner: str, evidence_ids: list[str], label: str = "Review data access exception") -> dict[str, Any]:
    name = compact(item.get("name") or item.get("requester") or item.get("dataset"))
    return row(prefix, index, name, compact(item.get("owner")) or owner, compact(item.get("description")) or compact(item.get("justification")) or f"{label}: {name}.", evidence_ids, severity=compact(item.get("severity")) or "medium", status=compact(item.get("status") or item.get("expiry")) or "open", expiry=compact(item.get("expiry") or item.get("expiration")), dataset=compact(item.get("dataset")), requester=compact(item.get("requester")))


def _named(value: Any, aliases: tuple[str, ...]) -> Any:
    if not isinstance(value, list):
        return value
    result = []
    for item in value:
        if isinstance(item, dict) and not compact(item.get("name")):
            item = {**item, "name": next((compact(item.get(key)) for key in aliases if compact(item.get(key))), "")}
        result.append(item)
    return result
