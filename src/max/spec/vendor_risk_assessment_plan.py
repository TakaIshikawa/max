"""Generate deterministic vendor risk assessment plans."""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "max.spec.vendor_risk_assessment_plan.v1"
KIND = "max.spec.vendor_risk_assessment_plan"


def generate_vendor_risk_assessment_plan(vendor_context: dict[str, Any]) -> dict[str, Any]:
    """Return a stable vendor risk assessment plan from structured vendor context."""
    ctx = _context(vendor_context)
    high_risk = ctx["criticality"] == "critical" or ctx["sensitive_data"] or ctx["regulated"]
    risk_rating = "high" if high_risk else "medium" if ctx["criticality"] == "important" else "low"
    review_cadence = "quarterly" if high_risk else "annual"

    controls = [
        f"Confirm DPA and security addendum for {ctx['vendor_name']}.",
        "Validate SOC 2 or equivalent independent security evidence.",
        "Record subprocessors, processing regions, and retention commitments.",
    ]
    if high_risk:
        controls.extend(
            [
                "Require security owner and legal approval before production data access.",
                "Escalate unresolved high findings to the risk committee.",
            ]
        )

    remediation_actions = [
        {
            "action": "Complete vendor questionnaire and evidence review.",
            "owner": ctx["security_owner"],
            "due": "before approval",
        },
        {
            "action": "Document contractual controls and renewal review date.",
            "owner": ctx["legal_owner"],
            "due": "before signature",
        },
    ]
    if high_risk:
        remediation_actions.append(
            {
                "action": "Define compensating controls for sensitive or regulated data exposure.",
                "owner": ctx["risk_owner"],
                "due": "before production use",
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "vendor_inventory": {
            "vendor_name": ctx["vendor_name"],
            "product": ctx["product"],
            "business_owner": ctx["business_owner"],
            "use_case": ctx["use_case"],
        },
        "criticality": ctx["criticality"],
        "data_access": {
            "data_categories": ctx["data_categories"],
            "sensitive_data": ctx["sensitive_data"],
            "regulated_context": ctx["regulated"],
        },
        "security_evidence": ctx["security_evidence"],
        "contractual_controls": controls,
        "risk_rating": risk_rating,
        "review_cadence": review_cadence,
        "remediation_actions": remediation_actions,
        "approval_gates": [
            {"gate": "security_review", "owner": ctx["security_owner"], "required": True},
            {"gate": "legal_review", "owner": ctx["legal_owner"], "required": True},
            {"gate": "executive_risk_acceptance", "owner": ctx["risk_owner"], "required": high_risk},
        ],
    }


def _context(value: dict[str, Any]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    data_categories = _list(raw.get("data_categories")) or ["business contact data"]
    evidence = _list(raw.get("security_evidence")) or ["SOC 2 report", "penetration test summary"]
    text = " ".join(data_categories + _list(raw.get("regulations")) + [str(raw.get("use_case", ""))]).lower()
    sensitive = any(term in text for term in ("pii", "personal", "payment", "health", "credential", "secret"))
    regulated = bool(raw.get("regulated")) or any(
        term in text for term in ("gdpr", "hipaa", "sox", "pci", "regulated")
    )
    return {
        "vendor_name": _text(raw.get("vendor_name") or raw.get("vendor")) or "Unknown vendor",
        "product": _text(raw.get("product")) or "Unknown product",
        "business_owner": _text(raw.get("business_owner") or raw.get("owner")) or "Vendor owner",
        "use_case": _text(raw.get("use_case")) or "Support the approved business workflow.",
        "criticality": _text(raw.get("criticality")).lower() or "standard",
        "data_categories": data_categories,
        "security_evidence": evidence,
        "security_owner": _text(raw.get("security_owner")) or "Security owner",
        "legal_owner": _text(raw.get("legal_owner")) or "Legal owner",
        "risk_owner": _text(raw.get("risk_owner")) or "Risk owner",
        "sensitive_data": sensitive,
        "regulated": regulated,
    }


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    return []


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value not in (None, "") else ""
