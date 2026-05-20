"""Generate deterministic vendor continuity review plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.vendor_continuity_review_plan.v1"
KIND = "max.spec.vendor_continuity_review_plan"


def generate_vendor_continuity_review_plan(spec_like: Any) -> dict[str, Any]:
    """Return vendor reviews, continuity risks, mitigations, replacements, and signoffs."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec, "vendor_continuity_review")
    vendors = _vendors(hints.get("vendors") or spec.get("vendors"))
    evidence_ids = _evidence_ids(ctx)
    reviews = [_review(index, vendor, evidence_ids) for index, vendor in enumerate(vendors, start=1)]
    risks = _risks(reviews, hints.get("outage_risks") or spec.get("outage_risks"), evidence_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, vendor_count=len(vendors), critical_vendor_count=sum(1 for vendor in vendors if vendor["critical"]), continuity_risk_count=len(risks)),
        "vendor_reviews": reviews,
        "continuity_risks": risks,
        "mitigation_actions": _mitigations(reviews, risks, evidence_ids),
        "replacement_options": _replacement_options(reviews, evidence_ids),
        "signoffs": _signoffs(reviews, evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _review(index: int, vendor: dict[str, Any], evidence_ids: list[str]) -> dict[str, Any]:
    gaps = []
    if not vendor["contract_evidence"]:
        gaps.append("missing contract evidence")
    if not vendor["sla_evidence"]:
        gaps.append("missing SLA evidence")
    return {
        "id": f"VR{index}",
        "vendor": vendor["name"],
        "critical": vendor["critical"],
        "owner": vendor["owner"] or "vendor_owner",
        "support_commitment": vendor["support_commitment"] or "support commitment pending review",
        "contract_evidence": vendor["contract_evidence"],
        "sla_evidence": vendor["sla_evidence"],
        "review_gaps": gaps,
        "priority": "critical" if vendor["critical"] else "standard",
        "evidence_reference_ids": evidence_ids,
    }


def _risks(reviews: list[dict[str, Any]], raw_risks: Any, evidence_ids: list[str]) -> list[dict[str, Any]]:
    risks = [
        {
            "id": f"CR{index}",
            "vendor": review["vendor"],
            "severity": "critical" if review["critical"] else "medium",
            "risk": f"{review['vendor']} continuity depends on closing review gaps: {', '.join(review['review_gaps'])}.",
            "evidence_reference_ids": evidence_ids,
        }
        for index, review in enumerate(reviews, start=1)
        if review["review_gaps"]
    ]
    for value in string_list(raw_risks):
        risks.append({"id": f"CR{len(risks) + 1}", "vendor": "cross_vendor", "severity": "high", "risk": value, "evidence_reference_ids": evidence_ids})
    return sorted(risks, key=lambda item: (item["severity"] != "critical", item["vendor"].casefold(), item["risk"].casefold()))


def _mitigations(reviews: list[dict[str, Any]], risks: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    actions = [
        {
            "id": f"MA{index}",
            "vendor": risk["vendor"],
            "owner": "vendor_owner",
            "action": f"Mitigate continuity risk: {risk['risk']}",
            "severity": risk["severity"],
            "evidence_reference_ids": evidence_ids,
        }
        for index, risk in enumerate(risks, start=1)
    ]
    if not actions:
        actions = [
            {
                "id": "MA1",
                "vendor": review["vendor"],
                "owner": review["owner"],
                "action": "Confirm continuity posture remains current during the next vendor review.",
                "severity": "low",
                "evidence_reference_ids": evidence_ids,
            }
            for review in reviews
        ]
    return actions


def _replacement_options(reviews: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"RO{index}",
            "vendor": review["vendor"],
            "owner": review["owner"],
            "strategy": "Maintain tested replacement or manual fallback." if review["critical"] else "Document viable replacement at next renewal.",
            "priority": "high" if review["critical"] else "medium",
            "evidence_reference_ids": evidence_ids,
        }
        for index, review in enumerate(reviews, start=1)
    ]


def _signoffs(reviews: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"SO{index}",
            "vendor": review["vendor"],
            "owner": review["owner"],
            "required": review["critical"] or bool(review["review_gaps"]),
            "signoff_signal": "Continuity owner accepts vendor support, contract, SLA, and replacement posture.",
            "evidence_reference_ids": evidence_ids,
        }
        for index, review in enumerate(reviews, start=1)
    ]


def _vendors(value: Any) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else []
    vendors: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            vendors.append(
                {
                    "name": compact(item.get("name") or item.get("vendor")) or f"vendor {index}",
                    "critical": _truthy(item.get("critical") or item.get("tier") == "critical"),
                    "owner": compact(item.get("owner")),
                    "support_commitment": compact(item.get("support_commitment") or item.get("support")),
                    "contract_evidence": compact(item.get("contract_evidence") or item.get("contract")),
                    "sla_evidence": compact(item.get("sla_evidence") or item.get("sla")),
                }
            )
        else:
            vendors.append({"name": compact(item) or f"vendor {index}", "critical": False, "owner": "", "support_commitment": "", "contract_evidence": "", "sla_evidence": ""})
    if not vendors:
        vendors.append({"name": "primary vendor", "critical": False, "owner": "", "support_commitment": "", "contract_evidence": "", "sla_evidence": ""})
    return sorted(vendors, key=lambda item: (not item["critical"], item["name"].casefold()))


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return compact(value).casefold() in {"1", "true", "yes", "y", "critical"}


def _hints(spec: dict[str, Any], key: str) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get(key)
    return hints if isinstance(hints, dict) else {}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
