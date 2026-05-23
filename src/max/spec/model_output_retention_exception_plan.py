"""Generate deterministic model output retention exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.model_output_retention_exception_plan.v1"
KIND = "max.spec.model_output_retention_exception_plan"


def generate_model_output_retention_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "model_output_retention_exception")
    categories = unique_records(
        named(
            hints.get("categories") or hints.get("retained_outputs") or hints.get("output_categories"),
            ("category", "model", "purpose", "dataset"),
        ),
        [{"name": "model output retention exception", "owner": "data_owner", "severity": "medium", "duration": "30 days"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, category_count=len(categories)),
        "retained_output_categories": [
            item(
                "MOR",
                index,
                record,
                "data_owner",
                evidence_ids,
                "Review retained model output category",
                name_keys=("name", "category", "model", "purpose", "dataset"),
                extra_keys=("category", "model", "purpose", "dataset", "duration"),
            )
            for index, record in enumerate(categories, start=1)
        ],
        "exception_rationale": section(hints, ("rationale", "exception_rationale", "justification"), "MOJ", "business_owner", "Document retention exception rationale", evidence_ids, ["time-boxed business, audit, or safety rationale for retaining model outputs"]),
        "retention_duration": section(hints, ("duration", "retention_duration", "retention_window"), "MOD", "data_owner", "Set retention duration", evidence_ids, ["default retention duration: 30 days"], extra_keys=("duration", "expires_at", "expiry")),
        "redaction_controls": section(hints, ("redaction_controls", "controls", "privacy_controls"), "MOC", "privacy_owner", "Operate redaction control", evidence_ids, ["PII redaction, prompt/output minimization, and encrypted storage"]),
        "access_review": section(hints, ("access_review", "reviewers", "access_reviewers"), "MOA", "security_owner", "Review retained output access", evidence_ids, ["data owner, privacy, security, and model owner reviewers"]),
        "monitoring": section(hints, ("monitoring", "monitors"), "MOM", "compliance_owner", "Monitor retention exception", evidence_ids, ["retention age, access drift, redaction failures, and export activity"]),
        "expiry_workflow": section(hints, ("expiry_workflow", "expiry", "expiration"), "MOX", "data_owner", "Expire retained model outputs", evidence_ids, ["purge outputs or renew exception before retention expiry"]),
        "evidence_references": ctx["evidence_references"],
    }
