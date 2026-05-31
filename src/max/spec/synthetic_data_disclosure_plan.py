"""Generate deterministic synthetic data disclosure plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.synthetic_data_disclosure_plan.v1"
KIND = "max.spec.synthetic_data_disclosure_plan"


def generate_synthetic_data_disclosure_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "synthetic_data_disclosure")
    datasets = unique_records(named(hints.get("datasets") or hints.get("generated_datasets"), ("dataset", "name")), [{"name": "synthetic dataset disclosure bootstrap", "generation_method": "unknown", "source_data_class": "unknown"}])
    datasets = sorted(datasets, key=lambda row: (_risk(row), compact(row.get("name")).casefold()))
    review = _review_actions(datasets, evidence_ids)
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": ctx["source"], "title": "Synthetic Data Disclosure Plan", "summary": source_summary(ctx, dataset_count=len(datasets), high_risk_count=sum(1 for row in datasets if _risk(row) == 0)), "generation_method": [item("SDM", i, row, "data_owner", evidence_ids, "Document synthetic data generation method", extra_keys=("generation_method", "source_data_class")) for i, row in enumerate(datasets, 1)], "source_constraints": section(hints, ("source_constraints", "constraints"), "SDS", "data_owner", "Document synthetic data source constraint", evidence_ids, ["source data classes, licenses, consent constraints, and prohibited reconstruction uses"]), "privacy_review": review, "downstream_labeling": section(hints, ("downstream_labeling", "labeling"), "SDL", "product_owner", "Label synthetic data downstream", evidence_ids, ["label generated records, derived features, exports, and evaluation artifacts as synthetic"]), "customer_disclosure": section(hints, ("customer_disclosure", "notifications", "consumer_notification"), "SDC", "compliance_owner", "Disclose synthetic data use", evidence_ids, ["customer-facing disclosure, contract notice, documentation update, and support response"]), "approval_actions": review if any(action["severity"] == "high" for action in review) else section(hints, ("approval_actions", "approvals"), "SDA", "compliance_owner", "Approve synthetic data disclosure", evidence_ids, ["data owner and privacy owner approve disclosure obligations"]), "evidence_references": ctx["evidence_references"]}


def _risk(row: dict[str, Any]) -> int:
    text = compact(row.get("source_data_class") or row.get("data_class")).lower()
    return 0 if any(term in text for term in ("sensitive", "regulated", "phi", "pii", "customer")) else 1


def _review_actions(datasets: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [item("SDP", i, {"name": compact(row.get("name")), "severity": "high" if _risk(row) == 0 else "medium", "description": "High-risk source data class requires explicit privacy review and approval before disclosure." if _risk(row) == 0 else "Complete privacy review for generation method, source constraints, and reconstruction risk."}, "privacy_owner", evidence_ids, "Review synthetic data privacy risk") for i, row in enumerate(datasets, 1)]
