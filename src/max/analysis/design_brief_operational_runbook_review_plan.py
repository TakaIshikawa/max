"""Deterministic operational runbook review plans for mapping-style design briefs."""

from __future__ import annotations

from typing import Any, Mapping

from max.analysis._design_brief_mapping_plan import evidence, first_text, gap, list_of_dicts, list_values, row_id, section, sorted_rows, text

KIND = "max.design_brief.operational_runbook_review_plan"
SCHEMA_VERSION = "max.design_brief.operational_runbook_review_plan.v1"


def generate_design_brief_operational_runbook_review_plan(brief: Mapping[str, Any]) -> dict[str, Any]:
    data = section(brief, "operational_runbook_review_plan")
    sections = _rows(data, "runbook_sections", "section", "RS")
    owners = _rows(data, "owners", "owner", "RO")
    escalation = _rows(data, "escalation_paths", "path", "EP")
    drills = _rows(data, "drills", "drill", "DR")
    missing = _missing(data)
    gaps = _gaps(sections, owners, missing)
    status = "blocked" if gaps else "ready"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {"readiness_status": status, "runbook_section_count": len(sections), "missing_procedure_count": len(missing), "gap_count": len(gaps)},
        "runbook_sections": sections,
        "owners": owners,
        "escalation_paths": escalation,
        "drill_schedule": drills,
        "missing_procedures": missing,
        "evidence_references": _refs(data, sections, owners, escalation, drills),
        "readiness_gaps": gaps,
    }


def _rows(data: Mapping[str, Any], field: str, label: str, prefix: str) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_items(data.get(field)), start=1):
        rows.append({"id": text(item.get("id"), row_id(prefix, index)), "name": first_text(item.get("name"), item.get(label), default=f"{label} {index}"), "owner": text(item.get("owner")), "status": text(item.get("status"), "pending"), "evidence_references": evidence(item.get("evidence_references") or item.get("evidence"))})
    return sorted_rows(rows, "name", "id")


def _missing(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_items(data.get("missing_procedures")), start=1):
        rows.append({"id": text(item.get("id"), row_id("MP", index)), "name": first_text(item.get("name"), item.get("procedure"), default=f"procedure {index}"), "owner": text(item.get("owner")), "severity": text(item.get("severity"), "high").casefold(), "evidence_references": evidence(item.get("evidence_references") or item.get("evidence"))})
    return sorted_rows(rows, "name", "id")


def _gaps(sections: list[dict[str, Any]], owners: list[dict[str, Any]], missing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps = []
    if not sections:
        gaps.append(gap("missing_runbook_sections", "No runbook sections were provided."))
    if not owners and not any(row["owner"] for row in sections):
        gaps.append(gap("missing_runbook_owners", "No runbook owners were provided."))
    for row in missing:
        gaps.append(gap(f"{_key(row['name'])}_missing_procedure", f"{row['name']} procedure is missing.", row["severity"]))
    return gaps


def _refs(data: Mapping[str, Any], *groups: list[dict[str, Any]]) -> list[str]:
    refs = evidence(data.get("evidence_references") or data.get("evidence"))
    for group in groups:
        for row in group:
            refs = evidence([*refs, *row["evidence_references"]])
    return refs


def _key(value: str) -> str:
    return "_".join(list_values(value.lower())) or "procedure"


def _items(value: Any) -> list[dict[str, Any]]:
    rows = list_of_dicts(value)
    if rows:
        return rows
    return [{"name": item} for item in list_values(value)]
