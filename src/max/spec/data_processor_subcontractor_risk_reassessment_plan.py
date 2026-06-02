"""Generate deterministic data processor subcontractor risk reassessment plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, summary
from max.spec._review_plan_common import base, ordered, row, unique_records, values

HIGH_RISK_JURISDICTIONS = {"china", "russia", "iran", "north korea", "belarus"}
SCHEMA_VERSION = "max.spec.data_processor_subcontractor_risk_reassessment_plan.v1"
KIND = "max.spec.data_processor_subcontractor_risk_reassessment_plan"


def generate_data_processor_subcontractor_risk_reassessment_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "data_processor_subcontractor_risk_reassessment")
    _require(hints, ("processor", "subcontractors", "jurisdictions", "data_categories", "owner", "legal_reviewer"))
    owner = compact(hints["owner"])
    legal = compact(hints["legal_reviewer"])
    subcontractors = unique_records(hints.get("subcontractors"), [])
    jurisdictions = values(hints.get("jurisdictions"), [])
    categories = values(hints.get("data_categories"), [])
    mitigations = values(hints.get("mitigation_requirements"), ["document compensating controls", "set follow-up review date"])

    jurisdiction_review = [row("DPSJ", index, jurisdiction, legal, f"Review transfer, residency, and subcontractor risk for {jurisdiction}.", evidence_ids, jurisdiction=jurisdiction) for index, jurisdiction in enumerate(jurisdictions, 1)]
    if any(jurisdiction.casefold() in HIGH_RISK_JURISDICTIONS for jurisdiction in jurisdictions):
        jurisdiction_review.append(row("DPSJ", len(jurisdiction_review) + 1, "High-risk jurisdiction escalation", legal, "Escalate high-risk jurisdiction exposure for privacy and security approval.", evidence_ids, severity="high"))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, processor=compact(hints["processor"]), reassessment_reason=compact(hints.get("reassessment_reason")) or "scheduled reassessment", subcontractor_count=len(subcontractors)),
        "inventory": [row("DPSI", index, compact(record["name"]), owner, f"Confirm subcontractor inventory entry for {compact(record['name'])}.", evidence_ids) for index, record in enumerate(subcontractors, 1)],
        "jurisdiction_review": jurisdiction_review,
        "data_category_review": [row("DPSD", index, category, owner, f"Confirm data category handling for {category}.", evidence_ids, data_category=category) for index, category in enumerate(categories, 1)],
        "contractual_review": [row("DPSC", 1, "Contractual controls review", legal, "Confirm DPA, subprocessors clause, audit rights, and notice obligations.", evidence_ids, required=True)],
        "mitigation": [row("DPSM", index, mitigation, owner, f"Track mitigation requirement: {mitigation}.", evidence_ids) for index, mitigation in enumerate(mitigations, 1)],
        "approval": [row("DPSA", 1, "Risk reassessment approval", legal, "Approve processor subcontractor risk reassessment before accepting continued processing.", evidence_ids, required=True)],
        "evidence_references": ctx["evidence_references"],
    }


def _require(hints: dict[str, Any], keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if not values(hints.get(key), [])]
    if missing:
        raise ValueError(f"Missing data processor subcontractor risk reassessment fields: {', '.join(ordered(missing))}")
