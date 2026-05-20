"""Deterministic contract renewal risk plans for mapping-style design briefs."""

from __future__ import annotations

from typing import Any, Mapping

from max.analysis._design_brief_mapping_plan import evidence, first_text, gap, list_of_dicts, row_id, section, sorted_rows, text

KIND = "max.design_brief.contract_renewal_risk_plan"
SCHEMA_VERSION = "max.design_brief.contract_renewal_risk_plan.v1"


def generate_design_brief_contract_renewal_risk_plan(brief: Mapping[str, Any]) -> dict[str, Any]:
    data = section(brief, "contract_renewal_risk_plan")
    accounts = _accounts(data)
    gaps = _gaps(accounts)
    high_unmitigated = any(row["risk_level"] == "high" and not row["mitigation_owner"] for row in accounts)
    status = "blocked" if high_unmitigated or any(item["severity"] == "high" for item in gaps) else ("needs_attention" if gaps else "ready")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {"readiness_status": status, "renewal_count": len(accounts), "gap_count": len(gaps)},
        "renewal_risks": accounts,
        "renewal_gaps": gaps,
    }


def _accounts(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(list_of_dicts(data.get("renewal_accounts") or data.get("accounts")), start=1):
        risk_drivers = sorted(evidence(item.get("risk_drivers") or item.get("risks")), key=str.casefold)
        rows.append(
            {
                "id": text(item.get("id"), row_id("RR", index)),
                "account": first_text(item.get("account"), item.get("name"), default=f"renewal account {index}"),
                "renewal_date": text(item.get("renewal_date") or item.get("contract_date")),
                "risk_level": text(item.get("risk_level") or item.get("severity"), "medium").lower(),
                "risk_drivers": risk_drivers,
                "success_criteria": evidence(item.get("success_criteria")),
                "mitigation_owner": text(item.get("mitigation_owner") or item.get("owner")),
                "escalation_needed": bool(item.get("escalation_needed") or item.get("escalation")),
                "evidence_references": evidence(item.get("evidence_references") or item.get("evidence")),
            }
        )
    return sorted_rows(rows, "renewal_date", "account")


def _gaps(accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps = []
    if not accounts:
        return [gap("missing_renewal_accounts", "No renewal accounts were provided.")]
    for row in accounts:
        prefix = row["account"].lower().replace(" ", "_")
        if not row["renewal_date"]:
            gaps.append(gap(f"{prefix}_missing_renewal_date", f"{row['account']} is missing a renewal date."))
        if not row["success_criteria"]:
            gaps.append(gap(f"{prefix}_missing_success_criteria", f"{row['account']} is missing renewal success criteria.", "medium"))
        if not row["mitigation_owner"]:
            gaps.append(gap(f"{prefix}_missing_mitigation_owner", f"{row['account']} is missing a mitigation owner."))
    return gaps
