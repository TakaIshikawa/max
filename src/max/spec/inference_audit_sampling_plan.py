"""Generate deterministic inference audit sampling plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.inference_audit_sampling_plan.v1"
KIND = "max.spec.inference_audit_sampling_plan"


def generate_inference_audit_sampling_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "inference_audit_sampling")
    categories = unique_records(named(hints.get("categories") or hints.get("sampling_categories"), ("category", "name")), [{"name": "inference trace audit bootstrap", "risk": "unknown"}])
    categories = sorted(categories, key=lambda row: (_risk(row), compact(row.get("name")).casefold()))
    privacy_filters = section(hints, ("privacy_filters", "filters"), "IAF", "privacy_owner", "Apply inference audit privacy filter", evidence_ids, ["redact secrets, direct identifiers, payment data, health data, and tenant-isolated fields"])
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": ctx["source"], "title": "Inference Audit Sampling Plan", "summary": source_summary(ctx, category_count=len(categories), high_risk_count=sum(1 for row in categories if _risk(row) == 0), missing_privacy_filter=not any(key in hints for key in ("privacy_filters", "filters"))), "sampling_strategy": [item("IAS", i, row, "audit_owner", evidence_ids, "Define inference audit sampling strategy", name_keys=("name", "category"), extra_keys=("risk", "sample_rate", "volume")) for i, row in enumerate(categories, 1)], "exclusions": section(hints, ("exclusions", "excluded"), "IAX", "privacy_owner", "Define inference audit exclusion", evidence_ids, ["exclude traces under legal hold conflict, unsupported tenant permissions, or unsafe reviewer exposure"]), "privacy_filters": privacy_filters, "reviewer_workflow": section(hints, ("reviewer_workflow", "reviewers"), "IAR", "audit_owner", "Assign inference audit reviewer workflow", evidence_ids, ["assign reviewers, calibrate labels, double-review high-risk samples, and track adjudication"]), "defect_taxonomy": section(hints, ("defect_taxonomy", "defects"), "IAD", "audit_owner", "Define inference audit defect label", evidence_ids, ["privacy leak, unsafe answer, hallucination, policy miss, tool misuse, and escalation miss"]), "escalation_thresholds": section(hints, ("escalation_thresholds", "thresholds"), "IAE", "audit_owner", "Define inference audit escalation threshold", evidence_ids, ["escalate on severe defect, repeated privacy issue, or defect-rate threshold breach"]), "reporting_cadence": section(hints, ("reporting_cadence", "cadence"), "IAC", "audit_owner", "Report inference audit sampling results", evidence_ids, ["weekly defect summary, monthly trend review, and release-blocker report"]), "risk_flags": _flags(categories, bool(hints.get("privacy_filters") or hints.get("filters")), evidence_ids), "evidence_references": ctx["evidence_references"]}


def _risk(row: dict[str, Any]) -> int:
    text = f"{compact(row.get('risk'))} {compact(row.get('category'))} {compact(row.get('name'))}".lower()
    return 0 if any(term in text for term in ("high", "safety", "regulated", "privacy", "abuse")) else 1


def _flags(categories: list[dict[str, Any]], has_filters: bool, evidence_ids: list[str]) -> list[dict[str, Any]]:
    flags = [item("IAQ", i, {"name": compact(row.get("name")), "severity": "high", "description": "High-risk inference category requires priority sampling and reviewer escalation."}, "audit_owner", evidence_ids, "Flag inference audit sampling risk") for i, row in enumerate([row for row in categories if _risk(row) == 0], 1)]
    if not has_filters:
        flags.append(item("IAQ", len(flags) + 1, {"name": "missing privacy filters", "severity": "high", "description": "Missing privacy filters must be defined before reviewer sampling starts."}, "privacy_owner", evidence_ids, "Flag inference audit sampling risk"))
    return flags or [item("IAQ", 1, {"name": "sampling inputs ready", "severity": "low"}, "audit_owner", evidence_ids, "Record inference audit sampling readiness")]
