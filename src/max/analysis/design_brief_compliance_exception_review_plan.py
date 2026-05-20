"""Deterministic compliance exception review plans for mapping-style design briefs."""

from __future__ import annotations

from typing import Any, Mapping

from max.analysis._design_brief_mapping_plan import (
    evidence,
    first_text,
    gap,
    list_of_dicts,
    list_values,
    row_id,
    section,
    sorted_rows,
    text,
)

KIND = "max.design_brief.compliance_exception_review_plan"
SCHEMA_VERSION = "max.design_brief.compliance_exception_review_plan.v1"


def generate_design_brief_compliance_exception_review_plan(
    brief: Mapping[str, Any],
) -> dict[str, Any]:
    data = section(brief, "compliance_exception_review_plan")
    exceptions = _exceptions(data)
    owners = _owners(data, exceptions)
    cadence = text(data.get("review_cadence") or data.get("cadence"))
    controls = _controls(data)
    gaps = _gaps(exceptions, owners, cadence)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "exception_count": len(exceptions),
            "owner_count": len(owners),
            "compensating_control_count": len(controls),
            "readiness_gap_count": len(gaps),
        },
        "exception_rows": exceptions,
        "owners": owners,
        "review_cadence": {"cadence": cadence, "owner": text(data.get("review_owner"))},
        "compensating_controls": controls,
        "evidence_references": _all_evidence(exceptions, owners, controls, data),
        "readiness_gaps": gaps,
    }


def _exceptions(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_items(data.get("exceptions") or data.get("exception_rows")), start=1):
        rows.append(
            {
                "id": text(item.get("id"), row_id("CE", index)),
                "name": first_text(
                    item.get("name"), item.get("exception"), item.get("scope"), default=f"exception {index}"
                ),
                "owner": text(item.get("owner")),
                "status": text(item.get("status"), "pending_review"),
                "expiry": text(item.get("expiry") or item.get("expiry_date")),
                "severity": text(item.get("severity"), "high"),
                "evidence_references": evidence(item.get("evidence_references") or item.get("evidence")),
            }
        )
    return sorted_rows(rows, "name", "id")


def _owners(data: Mapping[str, Any], exceptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_items(data.get("owners") or data.get("approvers")), start=1):
        rows.append(
            {
                "id": text(item.get("id"), row_id("OWN", index)),
                "name": first_text(item.get("name"), item.get("owner"), default=f"owner {index}"),
                "role": text(item.get("role"), "exception owner"),
                "evidence_references": evidence(item.get("evidence_references") or item.get("evidence")),
            }
        )
    seen = {row["name"].casefold() for row in rows}
    for item in exceptions:
        if item["owner"] and item["owner"].casefold() not in seen:
            rows.append(
                {
                    "id": row_id("OWN", len(rows) + 1),
                    "name": item["owner"],
                    "role": "exception owner",
                    "evidence_references": item["evidence_references"],
                }
            )
            seen.add(item["owner"].casefold())
    return sorted_rows(rows, "name", "id")


def _controls(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(
        _items(data.get("compensating_controls") or data.get("controls")), start=1
    ):
        rows.append(
            {
                "id": text(item.get("id"), row_id("CC", index)),
                "name": first_text(item.get("name"), item.get("control"), default=f"control {index}"),
                "owner": text(item.get("owner")),
                "evidence_references": evidence(item.get("evidence_references") or item.get("evidence")),
            }
        )
    return sorted_rows(rows, "name", "id")


def _all_evidence(
    exceptions: list[dict[str, Any]],
    owners: list[dict[str, Any]],
    controls: list[dict[str, Any]],
    data: Mapping[str, Any],
) -> list[str]:
    refs = evidence(data.get("evidence_references") or data.get("evidence"))
    for row in [*exceptions, *owners, *controls]:
        refs = evidence([*refs, *row["evidence_references"]])
    return refs


def _gaps(
    exceptions: list[dict[str, Any]], owners: list[dict[str, Any]], cadence: str
) -> list[dict[str, Any]]:
    gaps = []
    if not exceptions:
        gaps.append(gap("missing_compliance_exceptions", "No compliance exceptions were provided."))
    if not owners and not any(row["owner"] for row in exceptions):
        gaps.append(gap("missing_exception_owners", "No compliance exception owners were provided."))
    if not cadence:
        gaps.append(gap("missing_review_cadence", "No compliance exception review cadence was provided."))
    for row in exceptions:
        if not row["owner"]:
            gaps.append(gap(f"{_key(row['name'])}_missing_owner", f"{row['name']} is missing an owner."))
    return gaps


def _key(value: str) -> str:
    return "_".join(list_values(value.lower())) or "exception"


def _items(value: Any) -> list[dict[str, Any]]:
    rows = list_of_dicts(value)
    if rows:
        return rows
    return [{"name": item} for item in list_values(value)]
