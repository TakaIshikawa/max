"""Deterministic data quality remediation plans for mapping-style design briefs."""

from __future__ import annotations

from typing import Any, Mapping

from max.analysis._design_brief_mapping_plan import evidence, first_text, gap, list_of_dicts, list_values, row_id, section, sorted_rows, text

KIND = "max.design_brief.data_quality_remediation_plan"
SCHEMA_VERSION = "max.design_brief.data_quality_remediation_plan.v1"


def generate_design_brief_data_quality_remediation_plan(brief: Mapping[str, Any]) -> dict[str, Any]:
    data = section(brief, "data_quality_remediation_plan")
    defects = _defects(data)
    datasets = _rows(data, "affected_datasets", "dataset", "DS")
    owners = _rows(data, "remediation_owners", "owner", "RO")
    checks = _rows(data, "validation_checks", "check", "VC")
    gaps = _gaps(defects, owners, checks)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {"defect_class_count": len(defects), "affected_dataset_count": len(datasets), "validation_check_count": len(checks), "gap_count": len(gaps)},
        "defect_classes": defects,
        "affected_datasets": datasets,
        "remediation_owners": owners,
        "validation_checks": checks,
        "due_dates": sorted(list_values(data.get("due_dates") or data.get("due_date")), key=str.casefold),
        "evidence_references": _refs(data, defects, datasets, owners, checks),
        "readiness_gaps": gaps,
    }


def _defects(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_items(data.get("defect_classes") or data.get("defects")), start=1):
        rows.append({"id": text(item.get("id"), row_id("DQ", index)), "name": first_text(item.get("name"), item.get("defect"), default=f"defect {index}"), "severity": text(item.get("severity"), "medium").casefold(), "owner": text(item.get("owner")), "due_date": text(item.get("due_date") or item.get("due")), "evidence_references": evidence(item.get("evidence_references") or item.get("evidence"))})
    return sorted_rows(rows, "name", "id")


def _rows(data: Mapping[str, Any], field: str, label: str, prefix: str) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_items(data.get(field)), start=1):
        rows.append({"id": text(item.get("id"), row_id(prefix, index)), "name": first_text(item.get("name"), item.get(label), default=f"{label} {index}"), "owner": text(item.get("owner")), "due_date": text(item.get("due_date") or item.get("due")), "evidence_references": evidence(item.get("evidence_references") or item.get("evidence"))})
    return sorted_rows(rows, "name", "id")


def _gaps(defects: list[dict[str, Any]], owners: list[dict[str, Any]], checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps = []
    if not defects:
        gaps.append(gap("missing_defect_classes", "No data quality defect classes were provided."))
    if not checks:
        gaps.append(gap("missing_validation_checks", "No remediation validation checks were provided."))
    owner_names = {row["name"].casefold() for row in owners}
    for row in defects:
        if row["severity"] == "high" and not row["owner"] and not owner_names:
            gaps.append(gap(f"{_key(row['name'])}_missing_owner", f"{row['name']} high-severity defect is missing an owner."))
        if row["severity"] == "high" and not checks:
            gaps.append(gap(f"{_key(row['name'])}_missing_validation", f"{row['name']} high-severity defect is missing validation checks."))
    return gaps


def _refs(data: Mapping[str, Any], *groups: list[dict[str, Any]]) -> list[str]:
    refs = evidence(data.get("evidence_references") or data.get("evidence"))
    for group in groups:
        for row in group:
            refs = evidence([*refs, *row["evidence_references"]])
    return refs


def _key(value: str) -> str:
    return "_".join(list_values(value.lower())) or "defect"


def _items(value: Any) -> list[dict[str, Any]]:
    rows = list_of_dicts(value)
    if rows:
        return rows
    return [{"name": item} for item in list_values(value)]
