"""Generate profile deprecation sunset plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base

SCHEMA_VERSION = "max.spec.profile_deprecation_sunset_plan.v1"
KIND = "max.spec.profile_deprecation_sunset_plan"


def generate_profile_deprecation_sunset_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, hints, evidence_ids = base(spec_like, "profile_deprecation_sunset")
    rows = _rows(hints) or _rows(spec)
    profiles = [_profile(row, i, evidence_ids) for i, row in enumerate(rows, 1)]
    deprecated = [row for row in profiles if row["deprecated"]]
    blocked = [row for row in deprecated if row["blocking"]]
    replacement_ready = [row for row in deprecated if row["replacement_profile"] and not row["blocking"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": {"deprecated_count": len(deprecated), "blocked_count": len(blocked), "replacement_ready_count": len(replacement_ready)},
        "sunset_profiles": profiles,
        "migration_actions": [{"id": f"PDSM{i}", "profile_id": row["profile_id"], "action": "migrate consumers to replacement profile" if row["replacement_profile"] else "archive profile without replacement after evidence export", "replacement_profile": row["replacement_profile"], "evidence_reference_ids": evidence_ids} for i, row in enumerate(deprecated, 1)],
        "schedule_updates": [{"id": f"PDSS{i}", "profile_id": row["profile_id"], "action": "disable or reroute active scheduled runs", "evidence_reference_ids": evidence_ids} for i, row in enumerate(blocked, 1)],
        "archive_checks": [{"id": f"PDSA{i}", "profile_id": row["profile_id"], "check": "archive profile evidence and deprecation rationale", "evidence_reference_ids": evidence_ids} for i, row in enumerate(deprecated or profiles[:1], 1)],
        "verification_gates": [{"id": "PDSV1", "check": "deprecated profiles have no active schedules before sunset", "evidence_reference_ids": evidence_ids}],
        "evidence_references": ctx["evidence_references"],
    }


def _rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    value = source.get("profiles") if isinstance(source, dict) else None
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _profile(row: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    deprecated = bool(row.get("deprecated") or compact(row.get("status")).lower() == "deprecated")
    active = bool(row.get("active_schedule") or row.get("active_scheduled_runs") or row.get("scheduled_runs"))
    replacement = compact(row.get("replacement") or row.get("replacement_profile"))
    return {"id": f"PDS{index}", "profile_id": compact(row.get("id") or row.get("profile_id") or row.get("name")) or f"profile-{index}", "deprecated": deprecated, "active_schedule": active, "replacement_profile": replacement, "blocking": deprecated and active, "owner": compact(row.get("owner")) or "profile_owner", "evidence_reference_ids": evidence_ids}
