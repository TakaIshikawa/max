"""Generate deterministic human feedback data minimization plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.human_feedback_data_minimization_plan.v1"
KIND = "max.spec.human_feedback_data_minimization_plan"


def generate_human_feedback_data_minimization_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "human_feedback_data_minimization")
    fields = unique_records(
        named(hints.get("feedback_fields") or hints.get("fields") or hints.get("data_fields"), ("field", "data")),
        [
            {
                "name": "review score and rationale",
                "field": "review_score, rationale",
                "action": "keep minimum audit fields",
                "purpose": "learning and audit",
            }
        ],
    )
    risks = list(hints.get("risks") or [])
    if any("identity" in str(record).lower() or "reviewer" in str(record).lower() for record in fields):
        risks.append(
            {
                "name": "reviewer identity exposure",
                "severity": "high",
                "description": "Reviewer identifiers require redaction, hashing, or strict audit-only access.",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, field_count=len(fields)),
        "feedback_fields": [
            item(
                "HFM",
                index,
                record,
                "data_governance_owner",
                evidence_ids,
                "Minimize human feedback field",
                name_keys=("name", "field", "data"),
                extra_keys=("field", "action", "purpose", "classification"),
            )
            for index, record in enumerate(fields, start=1)
        ],
        "retention_purpose": section(
            hints,
            ("retention_purpose", "purposes", "purpose"),
            "HFP",
            "data_governance_owner",
            "Document human feedback retention purpose",
            evidence_ids,
            ["retain only fields needed for model learning, quality audit, dispute review, or legal hold"],
        ),
        "redaction_rules": section(
            hints,
            ("redaction_rules", "redactions", "redact"),
            "HFR",
            "privacy_owner",
            "Apply human feedback redaction rule",
            evidence_ids,
            ["redact reviewer identity, customer identifiers, free-text secrets, and unnecessary raw prompt text"],
        ),
        "aggregation_strategy": section(
            hints,
            ("aggregation_strategy", "aggregation", "aggregate"),
            "HFA",
            "analytics_owner",
            "Aggregate minimized human feedback",
            evidence_ids,
            ["aggregate by rubric dimension, cohort, model version, and time bucket when row-level data is unnecessary"],
        ),
        "reviewer_identity_handling": section(
            hints,
            ("reviewer_identity_handling", "reviewer_identity", "identity_handling"),
            "HFI",
            "privacy_owner",
            "Handle reviewer identity",
            evidence_ids,
            ["hash or redact reviewer identity except for time-boxed audit investigations"],
        ),
        "owner_checklist": section(
            hints,
            ("owner_checklist", "checklist", "owners"),
            "HFO",
            "program_owner",
            "Complete human feedback minimization checklist",
            evidence_ids,
            ["data owner, privacy owner, ML owner, and audit owner approve minimized storage"],
        ),
        "evidence": section(
            hints,
            ("evidence", "verification_evidence", "audit_evidence"),
            "HFE",
            "compliance_owner",
            "Collect human feedback minimization evidence",
            evidence_ids,
            ["field inventory, deletion proof, redaction samples, aggregation query, and audit log"],
        ),
        "risks": section({"risks": risks}, ("risks",), "HFK", "risk_owner", "Review minimization risk", evidence_ids, []),
        "acceptance_criteria": section(
            hints,
            ("acceptance_criteria", "approval_criteria"),
            "HFC",
            "program_owner",
            "Accept human feedback minimization",
            evidence_ids,
            ["minimization verification completed, reviewer identity handled, and audit evidence attached"],
        ),
        "evidence_references": ctx["evidence_references"],
    }
