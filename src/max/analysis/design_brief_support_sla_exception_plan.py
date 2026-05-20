"""Deterministic support SLA exception plans for mapping-style design briefs."""

from __future__ import annotations

from typing import Any, Mapping

from max.analysis._design_brief_mapping_plan import evidence, first_text, gap, list_of_dicts, list_values, row_id, section, sorted_rows, text

KIND = "max.design_brief.support_sla_exception_plan"
SCHEMA_VERSION = "max.design_brief.support_sla_exception_plan.v1"


def generate_design_brief_support_sla_exception_plan(brief: Mapping[str, Any]) -> dict[str, Any]:
    data = section(brief, "support_sla_exception_plan")
    exceptions = _rows(data, "exceptions", "exception", "SE")
    segments = _rows(data, "affected_segments", "segment", "AS")
    coverage = _rows(data, "coverage_rules", "rule", "CR")
    owners = _rows(data, "escalation_owners", "owner", "EO")
    review_dates = sorted(list_values(data.get("review_dates") or data.get("review_date")), key=str.casefold)
    gaps = _gaps(coverage, owners, review_dates)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {"exception_count": len(exceptions), "affected_segment_count": len(segments), "coverage_rule_count": len(coverage), "gap_count": len(gaps)},
        "exception_rows": exceptions,
        "affected_segments": segments,
        "coverage_rules": coverage,
        "escalation_owners": owners,
        "review_dates": review_dates,
        "evidence_references": _refs(data, exceptions, segments, coverage, owners),
        "readiness_gaps": gaps,
    }


def _rows(data: Mapping[str, Any], field: str, label: str, prefix: str) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_items(data.get(field) or data.get(f"{field}_rows")), start=1):
        rows.append({"id": text(item.get("id"), row_id(prefix, index)), "name": first_text(item.get("name"), item.get(label), default=f"{label} {index}"), "owner": text(item.get("owner")), "evidence_references": evidence(item.get("evidence_references") or item.get("evidence"))})
    return sorted_rows(rows, "name", "id")


def _gaps(coverage: list[dict[str, Any]], owners: list[dict[str, Any]], review_dates: list[str]) -> list[dict[str, Any]]:
    gaps = []
    if not owners:
        gaps.append(gap("missing_escalation_owner", "No escalation owner was provided."))
    if not review_dates:
        gaps.append(gap("missing_review_date", "No SLA exception review date was provided."))
    if not coverage:
        gaps.append(gap("missing_coverage_rule", "No temporary coverage rule was provided."))
    return gaps


def _refs(data: Mapping[str, Any], *groups: list[dict[str, Any]]) -> list[str]:
    refs = evidence(data.get("evidence_references") or data.get("evidence"))
    for group in groups:
        for row in group:
            refs = evidence([*refs, *row["evidence_references"]])
    return refs


def _items(value: Any) -> list[dict[str, Any]]:
    rows = list_of_dicts(value)
    if rows:
        return rows
    return [{"name": item} for item in list_values(value)]
