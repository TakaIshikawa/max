"""Generate deterministic AI safety evaluation exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.ai_safety_evaluation_exception_plan.v1"
KIND = "max.spec.ai_safety_evaluation_exception_plan"


def generate_ai_safety_evaluation_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "ai_safety_evaluation_exception")
    evaluations = unique_records(
        named(hints.get("evaluation_items") or hints.get("evaluations") or hints.get("deferred_evaluations"), ("evaluation", "model", "feature")),
        [{"name": "deferred safety evaluation", "owner": "ai_safety_owner", "severity": "high"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, evaluation_item_count=len(evaluations)),
        "evaluation_items": [item("ASE", index, record, "ai_safety_owner", evidence_ids, "Review deferred safety evaluation", name_keys=("name", "evaluation", "model", "feature"), extra_keys=("model", "feature", "risk")) for index, record in enumerate(evaluations, start=1)],
        "exception_rationale": section(hints, ("exception_rationale", "rationale", "justification"), "ASJ", "ai_safety_owner", "Document AI safety exception rationale", evidence_ids, ["time-boxed rationale for skipped or deferred evaluation"]),
        "model_feature_scope": section(hints, ("model_feature_scope", "scope", "features"), "ASS", "product_owner", "Confirm model or feature scope", evidence_ids, ["model, feature, and release scope"]),
        "safety_controls": section(hints, ("safety_controls", "controls", "risk_controls"), "ASC", "ai_safety_owner", "Operate AI safety control", evidence_ids, ["conservative safety review, limited rollout, and abuse monitoring"]),
        "approvals": section(hints, ("approvals", "reviewers", "approvers"), "ASA", "approval_owner", "Capture AI safety approval", evidence_ids, ["AI safety, product, security, and legal approval"]),
        "monitoring": section(hints, ("monitoring", "monitors"), "ASM", "ai_safety_owner", "Monitor safety exception", evidence_ids, ["post-launch safety telemetry and incident review"]),
        "rollback_triggers": section(hints, ("rollback_triggers", "rollback"), "ASR", "ai_safety_owner", "Define safety rollback trigger", evidence_ids, ["rollback on policy violation, incident spike, or harmful output rate increase"]),
        "evidence_references": ctx["evidence_references"],
    }
