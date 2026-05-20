"""Deterministic migration readiness plans for mapping-style design briefs."""

from __future__ import annotations

from typing import Any, Mapping

from max.analysis._design_brief_mapping_plan import evidence, first_text, gap, list_of_dicts, row_id, section, sorted_rows, text

KIND = "max.design_brief.migration_readiness_plan"
SCHEMA_VERSION = "max.design_brief.migration_readiness_plan.v1"


def generate_design_brief_migration_readiness_plan(brief: Mapping[str, Any]) -> dict[str, Any]:
    data = section(brief, "migration_readiness_plan")
    cohorts = _cohorts(data)
    blockers = _blockers(data)
    gaps = _gaps(data, cohorts, blockers)
    status = "blocked" if blockers or any(item["severity"] == "high" for item in gaps) else ("needs_attention" if gaps else "ready")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {"readiness_status": status, "migration_cohort_count": len(cohorts), "blocker_count": len(blockers), "gap_count": len(gaps)},
        "migration_cohorts": cohorts,
        "blockers": blockers,
        "communications": sorted(evidence(data.get("communications")), key=str.casefold),
        "validation_checks": sorted(evidence(data.get("validation_checks")), key=str.casefold),
        "readiness_gaps": gaps,
    }


def _cohorts(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(list_of_dicts(data.get("migration_cohorts") or data.get("cohorts")), start=1):
        rows.append(
            {
                "id": text(item.get("id"), row_id("MR", index)),
                "cohort": first_text(item.get("cohort"), item.get("name"), default=f"migration cohort {index}"),
                "source_environment": text(item.get("source_environment") or item.get("source")),
                "target_environment": text(item.get("target_environment") or item.get("target")),
                "rollback_plan": text(item.get("rollback_plan") or item.get("rollback")),
                "owner": text(item.get("owner")),
                "evidence_references": evidence(item.get("evidence_references") or item.get("evidence")),
            }
        )
    return sorted_rows(rows, "cohort")


def _blockers(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    return sorted_rows(
        [
            {"id": text(item.get("id"), row_id("BL", index)), "blocker": first_text(item.get("blocker"), item.get("name"), default=f"blocker {index}"), "owner": text(item.get("owner")), "evidence_references": evidence(item.get("evidence"))}
            for index, item in enumerate(list_of_dicts(data.get("blockers")), start=1)
        ],
        "blocker",
    )


def _gaps(data: Mapping[str, Any], cohorts: list[dict[str, Any]], blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not cohorts:
        return [gap("missing_migration_cohorts", "No migration cohorts were provided.")]
    gaps = []
    if not evidence(data.get("validation_checks")):
        gaps.append(gap("missing_validation_checks", "Migration validation checks are missing."))
    for row in cohorts:
        key = row["cohort"].lower().replace(" ", "_")
        if not row["rollback_plan"]:
            gaps.append(gap(f"{key}_missing_rollback_plan", f"{row['cohort']} is missing a rollback plan."))
        if not row["source_environment"] or not row["target_environment"]:
            gaps.append(gap(f"{key}_missing_environment_mapping", f"{row['cohort']} is missing source or target environment mapping.", "medium"))
    for row in blockers:
        if not row["owner"]:
            gaps.append(gap(f"{row['blocker'].lower().replace(' ', '_')}_missing_owner", f"{row['blocker']} is missing a blocker owner."))
    return gaps
