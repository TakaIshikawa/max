"""Generate deterministic external model provider exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.external_model_provider_exception_plan.v1"
KIND = "max.spec.external_model_provider_exception_plan"


def generate_external_model_provider_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "external_model_provider_exception")
    providers = unique_records(
        named(
            hints.get("providers") or hints.get("vendors") or hints.get("models"),
            ("provider", "vendor", "model"),
        ),
        [{"name": "external model provider", "owner": "ml_platform_owner", "severity": "medium"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, provider_count=len(providers)),
        "providers": [
            item(
                "EMP",
                index,
                record,
                "ml_platform_owner",
                evidence_ids,
                "Review external model provider exception",
                name_keys=("name", "provider", "vendor", "model"),
                extra_keys=("provider", "vendor", "model", "region", "purpose"),
            )
            for index, record in enumerate(providers, start=1)
        ],
        "exception_rationale": section(
            hints,
            ("exception_rationale", "rationale", "justification"),
            "EMR",
            "business_owner",
            "Document provider exception rationale",
            evidence_ids,
            [
                "time-boxed capability, availability, quality, or compliance rationale for "
                "using an external model provider"
            ],
        ),
        "data_sharing_scope": section(
            hints,
            ("data_sharing_scope", "shared_data", "data_shared", "data"),
            "EMD",
            "privacy_owner",
            "Define data sharing scope",
            evidence_ids,
            [
                "prompt, metadata, attachment, retention, residency, and customer data "
                "classification boundaries"
            ],
        ),
        "contractual_controls": section(
            hints,
            ("contractual_controls", "contracts", "controls"),
            "EMC",
            "legal_owner",
            "Confirm contractual control",
            evidence_ids,
            [
                "DPA, subprocessors, no-training commitment, retention limits, audit rights, "
                "and termination assistance"
            ],
        ),
        "security_review": section(
            hints,
            ("security_review", "security", "risk_review"),
            "EMS",
            "security_owner",
            "Complete security review",
            evidence_ids,
            [
                "vendor security review, encryption, access logging, network controls, and "
                "incident notification path"
            ],
        ),
        "budget_impact": section(
            hints,
            ("budget_impact", "budget", "cost"),
            "EMB",
            "finance_owner",
            "Assess provider budget impact",
            evidence_ids,
            [
                "forecast tokens, unit cost, spend cap, anomaly alert, and exception expiry "
                "budget review"
            ],
        ),
        "fallback_plan": section(
            hints,
            ("fallback_plan", "fallback_provider", "fallback"),
            "EMF",
            "ml_platform_owner",
            "Define fallback provider plan",
            evidence_ids,
            ["route to approved provider, local model, degraded workflow, or manual review path"],
        ),
        "approval_gates": section(
            hints,
            ("approval_gates", "approvals", "gates"),
            "EMA",
            "program_owner",
            "Gate provider exception approval",
            evidence_ids,
            [
                "business, legal, privacy, security, finance, and model owner approval "
                "before production use"
            ],
        ),
        "evidence_references": ctx["evidence_references"],
    }
