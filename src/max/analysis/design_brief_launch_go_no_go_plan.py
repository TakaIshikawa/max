"""Deterministic launch go/no-go plans for mapping-style design briefs."""

from __future__ import annotations

from typing import Any, Mapping

from max.analysis._design_brief_mapping_plan import evidence, first_text, gap, list_of_dicts, list_values, row_id, section, sorted_rows, text

KIND = "max.design_brief.launch_go_no_go_plan"
SCHEMA_VERSION = "max.design_brief.launch_go_no_go_plan.v1"


def generate_design_brief_launch_go_no_go_plan(brief: Mapping[str, Any]) -> dict[str, Any]:
    data = section(brief, "launch_go_no_go_plan")
    criteria = _criteria(data)
    approvers = _approvers(data)
    blockers = _blockers(data, criteria)
    rollback = _rollback_triggers(data)
    gaps = _gaps(criteria, approvers)
    decision = _decision(criteria, blockers, gaps)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "launch_decision": decision,
            "criteria_count": len(criteria),
            "blocker_count": len(blockers),
            "gap_count": len(gaps),
        },
        "launch_criteria": criteria,
        "gate_approvers": approvers,
        "blockers": blockers,
        "rollback_triggers": rollback,
        "evidence_references": _refs(data, criteria, approvers, blockers, rollback),
        "readiness_gaps": gaps,
    }


def _criteria(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_items(data.get("criteria") or data.get("launch_criteria")), start=1):
        rows.append(
            {
                "id": text(item.get("id"), row_id("LC", index)),
                "name": first_text(item.get("name"), item.get("criterion"), default=f"criterion {index}"),
                "owner": text(item.get("owner")),
                "severity": text(item.get("severity"), "medium").casefold(),
                "status": text(item.get("status"), "pending").casefold().replace(" ", "_"),
                "evidence_references": evidence(item.get("evidence_references") or item.get("evidence")),
            }
        )
    return sorted_rows(rows, "name", "id")


def _approvers(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_items(data.get("approvers") or data.get("gate_approvers")), start=1):
        rows.append({"id": text(item.get("id"), row_id("GA", index)), "name": first_text(item.get("name"), item.get("approver"), default=f"approver {index}"), "role": text(item.get("role"), "launch approver"), "decision": text(item.get("decision"), "pending").casefold().replace(" ", "_"), "evidence_references": evidence(item.get("evidence_references") or item.get("evidence"))})
    return sorted_rows(rows, "name", "id")


def _blockers(data: Mapping[str, Any], criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_items(data.get("blockers")), start=1):
        rows.append({"id": text(item.get("id"), row_id("BL", index)), "name": first_text(item.get("name"), item.get("blocker"), default=f"blocker {index}"), "owner": text(item.get("owner")), "severity": text(item.get("severity"), "high").casefold(), "status": text(item.get("status"), "open").casefold(), "evidence_references": evidence(item.get("evidence_references") or item.get("evidence"))})
    for criterion in criteria:
        if criterion["severity"] == "high" and criterion["status"] not in {"met", "passed", "approved"}:
            rows.append({"id": row_id("BL", len(rows) + 1), "name": f"Unresolved {criterion['name']}", "owner": criterion["owner"], "severity": "high", "status": "open", "evidence_references": criterion["evidence_references"]})
    return sorted_rows(rows, "name", "id")


def _rollback_triggers(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(
        _items(data.get("rollback_triggers") or data.get("rollback")), start=1
    ):
        rows.append({"id": text(item.get("id"), row_id("RT", index)), "name": first_text(item.get("name"), item.get("trigger"), default=f"trigger {index}"), "owner": text(item.get("owner")), "evidence_references": evidence(item.get("evidence_references") or item.get("evidence"))})
    return sorted_rows(rows, "name", "id")


def _decision(criteria: list[dict[str, Any]], blockers: list[dict[str, Any]], gaps: list[dict[str, Any]]) -> str:
    if any(row["severity"] == "high" and row["status"] == "open" for row in blockers):
        return "no_go"
    if gaps or any(row["status"] in {"pending", "conditional"} for row in criteria):
        return "conditional_go"
    return "go"


def _gaps(criteria: list[dict[str, Any]], approvers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps = []
    if not criteria:
        gaps.append(gap("missing_launch_criteria", "No launch criteria were provided."))
    if not approvers:
        gaps.append(gap("missing_gate_approvers", "No launch gate approvers were provided."))
    for row in criteria:
        if not row["owner"]:
            gaps.append(gap(f"{_key(row['name'])}_missing_owner", f"{row['name']} is missing an owner."))
    return gaps


def _refs(data: Mapping[str, Any], *groups: list[dict[str, Any]]) -> list[str]:
    refs = evidence(data.get("evidence_references") or data.get("evidence"))
    for group in groups:
        for row in group:
            refs = evidence([*refs, *row["evidence_references"]])
    return refs


def _key(value: str) -> str:
    return "_".join(list_values(value.lower())) or "criterion"


def _items(value: Any) -> list[dict[str, Any]]:
    rows = list_of_dicts(value)
    if rows:
        return rows
    return [{"name": item} for item in list_values(value)]
