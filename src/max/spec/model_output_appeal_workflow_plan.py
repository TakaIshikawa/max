"""Generate deterministic model output appeal workflow plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import section
from max.spec._review_plan_common import base, source_summary


SCHEMA_VERSION = "max.spec.model_output_appeal_workflow_plan.v1"
KIND = "max.spec.model_output_appeal_workflow_plan"


def generate_model_output_appeal_workflow_plan(spec_like: Any) -> dict[str, Any]:
    """Return a stable plan for disputed model output appeals."""
    _spec, ctx, hints, evidence_ids = base(spec_like, "model_output_appeal_workflow")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx),
        "appeal_intake": section(hints, ("appeal_intake", "intake_fields"), "MOI", "support_owner", "Capture appeal intake field", evidence_ids, ["output id, customer id, disputed decision, user rationale, requested remedy, and submission timestamp"]),
        "reviewer_roles": section(hints, ("reviewer_roles", "roles"), "MOR", "program_owner", "Assign appeal reviewer role", evidence_ids, ["privacy reviewer verifies sensitive data handling", "model reviewer evaluates output evidence and rubric fit", "product reviewer confirms customer impact and remedy"]),
        "evidence_requirements": section(hints, ("evidence_requirements", "evidence_packet"), "MOE", "quality_owner", "Collect appeal evidence packet", evidence_ids, ["prompt, model output, policy version, retrieval context, reviewer notes, and customer-provided evidence"]),
        "decision_slas": section(hints, ("decision_slas", "slas"), "MOS", "support_owner", "Set appeal decision SLA", evidence_ids, ["acknowledge within 1 business day and decide within 5 business days"]),
        "escalation_paths": section(hints, ("escalation_paths", "escalations"), "MOX", "program_owner", "Define appeal escalation path", evidence_ids, ["privacy, legal, safety, and executive escalation for high-risk disputes"]),
        "audit_logging": section(hints, ("audit_logging", "audit"), "MOL", "compliance_owner", "Log appeal audit event", evidence_ids, ["immutable appeal status, reviewer, evidence, decision, notification, and override trail"]),
        "notification_steps": section(hints, ("notification_steps", "notifications"), "MON", "support_owner", "Notify appeal participant", evidence_ids, ["receipt, review start, decision, remediation, and closure notifications"]),
        "evidence_references": ctx["evidence_references"],
    }
