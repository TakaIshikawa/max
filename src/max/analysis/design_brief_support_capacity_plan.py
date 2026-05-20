"""Deterministic support capacity plans for mapping-style design briefs."""

from __future__ import annotations

from typing import Any, Mapping

from max.analysis._design_brief_mapping_plan import evidence, first_text, gap, list_of_dicts, row_id, section, sorted_rows, text

KIND = "max.design_brief.support_capacity_plan"
SCHEMA_VERSION = "max.design_brief.support_capacity_plan.v1"


def generate_design_brief_support_capacity_plan(brief: Mapping[str, Any]) -> dict[str, Any]:
    data = section(brief, "support_capacity_plan")
    tiers = _tiers(data)
    gaps = _gaps(data, tiers)
    status = "blocked" if any(row["coverage_delta"] < 0 for row in tiers) else ("needs_attention" if gaps else "ready")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {"recommendation_status": status, "support_tier_count": len(tiers), "capacity_gap_count": len(gaps)},
        "capacity_by_tier": tiers,
        "capacity_gaps": gaps,
        "mitigation_actions": _mitigations(data, gaps),
    }


def _tiers(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(list_of_dicts(data.get("support_tiers") or data.get("tiers")), start=1):
        required = int(item.get("required_staff") or item.get("required") or 0)
        assigned = int(item.get("assigned_staff") or item.get("assigned") or item.get("staffing_coverage") or 0)
        rows.append(
            {
                "id": text(item.get("id"), row_id("SC", index)),
                "tier": first_text(item.get("tier"), item.get("name"), default=f"support tier {index}"),
                "expected_ticket_volume": int(item.get("expected_ticket_volume") or item.get("ticket_volume") or data.get("expected_ticket_volume") or 0),
                "required_staff": required,
                "assigned_staff": assigned,
                "coverage_delta": assigned - required,
                "escalation_load": text(item.get("escalation_load") or data.get("escalation_load")),
                "owner": text(item.get("owner")),
                "evidence_references": evidence(item.get("evidence_references") or item.get("evidence")),
            }
        )
    return sorted_rows(rows, "tier")


def _gaps(data: Mapping[str, Any], tiers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not tiers:
        return [gap("missing_support_tiers", "No support tiers were provided.")]
    gaps = []
    if not text(data.get("escalation_load")) and all(not row["escalation_load"] for row in tiers):
        gaps.append(gap("missing_escalation_load", "Escalation load assumptions are missing."))
    for row in tiers:
        if row["coverage_delta"] < 0:
            gaps.append(gap(f"{row['tier'].lower().replace(' ', '_')}_understaffed", f"{row['tier']} is understaffed by {abs(row['coverage_delta'])}."))
    return gaps


def _mitigations(data: Mapping[str, Any], gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = list_of_dicts(data.get("mitigation_actions") or data.get("mitigations"))
    if actions:
        return sorted_rows([{"id": text(item.get("id"), row_id("M", index)), "action": text(item.get("action") or item.get("description")), "owner": text(item.get("owner")), "evidence_references": evidence(item.get("evidence"))} for index, item in enumerate(actions, start=1)], "action")
    return [{"id": f"M{index}", "action": item["description"], "owner": "support lead", "evidence_references": []} for index, item in enumerate(gaps, start=1)]
