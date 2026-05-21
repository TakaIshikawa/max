"""Generate deterministic tenant offboarding readiness plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.tenant_offboarding_readiness_plan.v1"
KIND = "max.spec.tenant_offboarding_readiness_plan"


def generate_tenant_offboarding_readiness_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "tenant_offboarding_readiness")
    tenants = unique_records(
        hints.get("tenants"),
        [{"name": ctx["buyer"], "owner": "customer_success_owner", "severity": "medium"}],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, tenant_count=len(tenants)),
        "tenants": [_item("TOR", index, item, "customer_success_owner", evidence_ids) for index, item in enumerate(tenants, start=1)],
        "export_blockers": _section(hints, ("export_blockers", "exports"), "TOE", "data_export_owner", "Confirm tenant export blocker", evidence_ids, ["export manifest approval"]),
        "deletion_blockers": _section(hints, ("deletion_blockers", "deletions"), "TOD", "data_deletion_owner", "Resolve tenant deletion blocker", evidence_ids, ["retention exception review"]),
        "access_revocations": _section(hints, ("access_revocations", "revocations"), "TOA", "identity_owner", "Revoke tenant access", evidence_ids, ["service account revocation"]),
        "stakeholder_handoffs": _section(hints, ("stakeholder_handoffs", "handoffs", "ownership"), "TOH", "customer_success_owner", "Complete stakeholder handoff", evidence_ids, ["customer success handoff"]),
        "timelines": _section(hints, ("timelines", "milestones"), "TOT", "program_owner", "Track offboarding timeline", evidence_ids, ["offboarding completion window"]),
        "evidence_checks": _section(hints, ("evidence", "evidence_checks"), "TOEV", "compliance_owner", "Collect offboarding evidence", evidence_ids, ["export, deletion, and revocation evidence"]),
        "evidence_references": ctx["evidence_references"],
    }


def _section(
    hints: dict[str, Any],
    keys: tuple[str, ...],
    prefix: str,
    owner: str,
    description_prefix: str,
    evidence_ids: list[str],
    fallback: list[Any],
) -> list[dict[str, Any]]:
    value = next((hints[key] for key in keys if key in hints), None)
    return [
        _item(prefix, index, item, owner, evidence_ids, description_prefix)
        for index, item in enumerate(unique_records(value, fallback), start=1)
    ]


def _item(
    prefix: str,
    index: int,
    item: dict[str, Any],
    owner: str,
    evidence_ids: list[str],
    description_prefix: str = "Review tenant offboarding readiness for",
) -> dict[str, Any]:
    name = compact(item.get("name"))
    return row(
        prefix,
        index,
        name,
        compact(item.get("owner")) or owner,
        compact(item.get("description")) or f"{description_prefix}: {name}.",
        evidence_ids,
        severity=compact(item.get("severity")) or "medium",
        status=compact(item.get("status")) or compact(item.get("deadline_status")) or "open",
        deadline=compact(item.get("deadline") or item.get("due")),
    )
