"""Deterministic customer cutover rehearsal plans for mapping-style design briefs."""

from __future__ import annotations

from typing import Any, Mapping

from max.analysis._design_brief_mapping_plan import evidence, first_text, gap, list_of_dicts, list_values, row_id, section, sorted_rows, text

KIND = "max.design_brief.customer_cutover_rehearsal_plan"
SCHEMA_VERSION = "max.design_brief.customer_cutover_rehearsal_plan.v1"


def generate_design_brief_customer_cutover_rehearsal_plan(brief: Mapping[str, Any]) -> dict[str, Any]:
    data = section(brief, "customer_cutover_rehearsal_plan")
    windows = _rows(data, "rehearsal_windows", "window", "RW")
    participants = _rows(data, "participants", "participant", "PT")
    dependencies = _rows(data, "dependencies", "dependency", "DP")
    checks = _rows(data, "validation_checks", "check", "VC")
    contacts = _rows(data, "rollback_contacts", "contact", "RC")
    gaps = _gaps(windows, checks, contacts)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {"window_count": len(windows), "validation_check_count": len(checks), "rollback_contact_count": len(contacts), "gap_count": len(gaps)},
        "rehearsal_windows": windows,
        "participants": participants,
        "dependencies": dependencies,
        "validation_checks": checks,
        "rollback_contacts": contacts,
        "evidence_references": _refs(data, windows, participants, dependencies, checks, contacts),
        "readiness_gaps": gaps,
    }


def _rows(data: Mapping[str, Any], field: str, label: str, prefix: str) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_items(data.get(field)), start=1):
        rows.append({"id": text(item.get("id"), row_id(prefix, index)), "name": first_text(item.get("name"), item.get(label), item.get("window"), item.get("check"), default=f"{label} {index}"), "owner": text(item.get("owner")), "timing": text(item.get("timing") or item.get("date") or item.get("window")), "evidence_references": evidence(item.get("evidence_references") or item.get("evidence"))})
    return sorted_rows(rows, "name", "id")


def _gaps(windows: list[dict[str, Any]], checks: list[dict[str, Any]], contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps = []
    if not windows:
        gaps.append(gap("missing_rehearsal_window", "No rehearsal window was provided."))
    if not contacts:
        gaps.append(gap("missing_rollback_contact", "No rollback contact was provided."))
    for row in checks:
        if not row["owner"]:
            gaps.append(gap(f"{_key(row['name'])}_missing_owner", f"{row['name']} validation check is missing an owner."))
    return gaps


def _refs(data: Mapping[str, Any], *groups: list[dict[str, Any]]) -> list[str]:
    refs = evidence(data.get("evidence_references") or data.get("evidence"))
    for group in groups:
        for row in group:
            refs = evidence([*refs, *row["evidence_references"]])
    return refs


def _key(value: str) -> str:
    return "_".join(list_values(value.lower())) or "validation_check"


def _items(value: Any) -> list[dict[str, Any]]:
    rows = list_of_dicts(value)
    if rows:
        return rows
    return [{"name": item} for item in list_values(value)]
