"""Deterministic risk acceptance plans for mapping-style design briefs."""

from __future__ import annotations

from typing import Any, Mapping

from max.analysis._design_brief_mapping_plan import evidence, first_text, gap, list_of_dicts, list_values, row_id, section, sorted_rows, text

KIND = "max.design_brief.risk_acceptance_plan"
SCHEMA_VERSION = "max.design_brief.risk_acceptance_plan.v1"


def generate_design_brief_risk_acceptance_plan(brief: Mapping[str, Any]) -> dict[str, Any]:
    data = section(brief, "risk_acceptance_plan")
    risks = _risks(data)
    owners = _owners(data, risks)
    gaps = _gaps(risks, owners)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "accepted_count": sum(1 for row in risks if row["status"] == "accepted"),
            "pending_count": sum(1 for row in risks if row["status"] == "pending"),
            "expired_count": sum(1 for row in risks if row["status"] == "expired"),
            "gap_count": len(gaps),
        },
        "risk_rows": risks,
        "decision_owners": owners,
        "approval_evidence": _approval_evidence(data, risks),
        "readiness_gaps": gaps,
    }


def _risks(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_items(data.get("risks") or data.get("risk_rows")), start=1):
        status = text(item.get("status"), "pending").casefold().replace(" ", "_")
        rows.append(
            {
                "id": text(item.get("id"), row_id("RA", index)),
                "risk": first_text(item.get("risk"), item.get("name"), default=f"risk {index}"),
                "owner": text(item.get("owner") or item.get("decision_owner")),
                "status": status if status in {"accepted", "pending", "expired"} else "pending",
                "expiry": text(item.get("expiry") or item.get("expiry_date")),
                "mitigation": text(item.get("mitigation") or item.get("control")),
                "evidence_references": evidence(item.get("evidence_references") or item.get("evidence")),
            }
        )
    return sorted_rows(rows, "risk", "id")


def _owners(data: Mapping[str, Any], risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_items(data.get("decision_owners") or data.get("owners")), start=1):
        rows.append(
            {
                "id": text(item.get("id"), row_id("DO", index)),
                "name": first_text(item.get("name"), item.get("owner"), default=f"owner {index}"),
                "role": text(item.get("role"), "decision owner"),
                "evidence_references": evidence(item.get("evidence_references") or item.get("evidence")),
            }
        )
    seen = {row["name"].casefold() for row in rows}
    for risk in risks:
        if risk["owner"] and risk["owner"].casefold() not in seen:
            rows.append({"id": row_id("DO", len(rows) + 1), "name": risk["owner"], "role": "decision owner", "evidence_references": risk["evidence_references"]})
            seen.add(risk["owner"].casefold())
    return sorted_rows(rows, "name", "id")


def _approval_evidence(data: Mapping[str, Any], risks: list[dict[str, Any]]) -> list[str]:
    refs = evidence(data.get("approval_evidence") or data.get("evidence_references") or data.get("evidence"))
    for risk in risks:
        refs = evidence([*refs, *risk["evidence_references"]])
    return refs


def _gaps(risks: list[dict[str, Any]], owners: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps = []
    if not risks:
        gaps.append(gap("missing_risks", "No risk acceptance rows were provided."))
    if not owners and not any(row["owner"] for row in risks):
        gaps.append(gap("missing_decision_owners", "No risk acceptance decision owners were provided."))
    for risk in risks:
        key = _key(risk["risk"])
        if not risk["owner"]:
            gaps.append(gap(f"{key}_missing_owner", f"{risk['risk']} is missing a decision owner."))
        if risk["status"] == "accepted" and not risk["expiry"]:
            gaps.append(gap(f"{key}_missing_expiry", f"{risk['risk']} is accepted without an expiry.", "medium"))
        if not risk["mitigation"]:
            gaps.append(gap(f"{key}_missing_mitigation", f"{risk['risk']} is missing a mitigation.", "medium"))
    return gaps


def _key(value: str) -> str:
    return "_".join(list_values(value.lower())) or "risk"


def _items(value: Any) -> list[dict[str, Any]]:
    rows = list_of_dicts(value)
    if rows:
        return rows
    return [{"name": item} for item in list_values(value)]
