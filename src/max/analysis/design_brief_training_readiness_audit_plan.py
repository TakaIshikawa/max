"""Deterministic training readiness audit plans for mapping-style design briefs."""

from __future__ import annotations

from typing import Any, Mapping

from max.analysis._design_brief_mapping_plan import evidence, first_text, gap, list_of_dicts, list_values, row_id, section, sorted_rows, text

KIND = "max.design_brief.training_readiness_audit_plan"
SCHEMA_VERSION = "max.design_brief.training_readiness_audit_plan.v1"


def generate_design_brief_training_readiness_audit_plan(brief: Mapping[str, Any]) -> dict[str, Any]:
    data = section(brief, "training_readiness_audit_plan")
    cohorts = _rows(data, "learner_cohorts", "cohort", "LC")
    assets = _rows(data, "training_assets", "asset", "TA")
    facilitators = _rows(data, "facilitators", "facilitator", "FA")
    targets = _rows(data, "completion_targets", "target", "CT")
    checks = _rows(data, "assessment_checks", "check", "AC")
    gaps = _gaps(cohorts, assets, checks)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {"cohort_count": len(cohorts), "asset_count": len(assets), "assessment_check_count": len(checks), "gap_count": len(gaps)},
        "learner_cohorts": cohorts,
        "training_assets": assets,
        "facilitators": facilitators,
        "completion_targets": targets,
        "assessment_checks": checks,
        "evidence_references": _refs(data, cohorts, assets, facilitators, targets, checks),
        "readiness_gaps": gaps,
    }


def _rows(data: Mapping[str, Any], field: str, label: str, prefix: str) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_items(data.get(field)), start=1):
        rows.append({"id": text(item.get("id"), row_id(prefix, index)), "name": first_text(item.get("name"), item.get(label), default=f"{label} {index}"), "owner": text(item.get("owner")), "target": text(item.get("target") or item.get("due_date")), "evidence_references": evidence(item.get("evidence_references") or item.get("evidence"))})
    return sorted_rows(rows, "name", "id")


def _gaps(cohorts: list[dict[str, Any]], assets: list[dict[str, Any]], checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps = []
    if not cohorts:
        gaps.append(gap("missing_learner_cohorts", "No learner cohorts were provided."))
    if not assets:
        gaps.append(gap("missing_training_assets", "No training assets were provided."))
    for row in checks:
        if not row["owner"]:
            gaps.append(gap(f"{_key(row['name'])}_missing_owner", f"{row['name']} assessment check is missing an owner."))
    return gaps


def _refs(data: Mapping[str, Any], *groups: list[dict[str, Any]]) -> list[str]:
    refs = evidence(data.get("evidence_references") or data.get("evidence"))
    for group in groups:
        for row in group:
            refs = evidence([*refs, *row["evidence_references"]])
    return refs


def _key(value: str) -> str:
    return "_".join(list_values(value.lower())) or "assessment_check"


def _items(value: Any) -> list[dict[str, Any]]:
    rows = list_of_dicts(value)
    if rows:
        return rows
    return [{"name": item} for item in list_values(value)]
