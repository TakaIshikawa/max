"""Generate deterministic support coverage gap plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.support_coverage_gap_plan.v1"
KIND = "max.spec.support_coverage_gap_plan"


def generate_support_coverage_gap_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    windows = _windows(hints)
    unsupported = string_list(hints.get("unsupported_scenarios")) or [f"after-hours support for {ctx['target_user']}"]
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, coverage_window_count=len(windows), unsupported_scenario_count=len(unsupported), staffing_gap_count=len(unsupported)),
        "coverage_windows": [_window(index, window, evidence_ids) for index, window in enumerate(windows, start=1)],
        "unsupported_scenarios": [{"id": f"US{index}", "scenario": item, "owner": "support_owner", "evidence_reference_ids": evidence_ids} for index, item in enumerate(sorted(unsupported, key=str.casefold), start=1)],
        "staffing_gaps": _staffing_gaps(unsupported, evidence_ids),
        "escalation_paths": _escalations(hints, evidence_ids),
        "remediation_actions": _remediations(unsupported, evidence_ids),
        "readiness_checks": _readiness(hints, evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _windows(hints: dict[str, Any]) -> list[dict[str, str]]:
    raw = hints.get("coverage_windows") or hints.get("regions")
    values = [raw] if isinstance(raw, dict) else raw if isinstance(raw, list) else string_list(raw)
    rows = []
    for index, item in enumerate(values, start=1):
        if isinstance(item, dict):
            rows.append({"region": compact(item.get("region") or item.get("name")) or f"region {index}", "support_hours": compact(item.get("support_hours") or item.get("hours")) or "business hours", "tier_owner": compact(item.get("tier_owner") or item.get("owner")) or "support_owner"})
        else:
            rows.append({"region": compact(item) or f"region {index}", "support_hours": "business hours", "tier_owner": "support_owner"})
    if not rows:
        rows.append({"region": "primary region", "support_hours": "business hours", "tier_owner": "support_owner"})
    return sorted(rows, key=lambda row: row["region"].casefold())


def _window(index: int, window: dict[str, str], evidence_ids: list[str]) -> dict[str, Any]:
    return {"id": f"CW{index}", **window, "evidence_reference_ids": evidence_ids}


def _staffing_gaps(unsupported: list[str], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [{"id": f"SG{index}", "gap": item, "owner": "support_owner", "action": f"Assign coverage for {item}.", "evidence_reference_ids": evidence_ids} for index, item in enumerate(sorted(unsupported, key=str.casefold), start=1)]


def _escalations(hints: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    contacts = string_list(hints.get("escalation_contacts") or hints.get("escalation_paths")) or ["support_lead", "engineering_on_call"]
    return [{"id": f"EP{index}", "contact": contact, "condition": "support coverage gap or customer escalation", "evidence_reference_ids": evidence_ids} for index, contact in enumerate(sorted(contacts, key=str.casefold), start=1)]


def _remediations(unsupported: list[str], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [{"id": f"RA{index}", "action": f"Close support coverage gap for {item}.", "owner": "support_owner", "evidence_reference_ids": evidence_ids} for index, item in enumerate(sorted(unsupported, key=str.casefold), start=1)]


def _readiness(hints: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    checks = string_list(hints.get("readiness_checks")) or ["support playbook reviewed", "escalation contacts confirmed", "known unsupported scenarios documented"]
    return [{"id": f"RC{index}", "check": check, "owner": "support_owner", "evidence_reference_ids": evidence_ids} for index, check in enumerate(checks, start=1)]


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("support_coverage_gap")
    return hints if isinstance(hints, dict) else {}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
