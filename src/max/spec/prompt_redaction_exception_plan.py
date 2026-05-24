"""Generate deterministic prompt redaction exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.prompt_redaction_exception_plan.v1"
KIND = "max.spec.prompt_redaction_exception_plan"


def generate_prompt_redaction_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "prompt_redaction_exception")
    categories = unique_records(
        named(
            hints.get("exempt_prompt_categories") or hints.get("prompts") or hints.get("categories"),
            ("category", "prompt", "purpose", "dataset"),
        ),
        [{"name": "temporary prompt redaction exception", "owner": "privacy_owner", "severity": "high"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, exempt_prompt_category_count=len(categories)),
        "exempt_prompt_categories": [
            item(
                "PRE",
                index,
                record,
                "privacy_owner",
                evidence_ids,
                "Review prompt redaction exception category",
                name_keys=("name", "category", "prompt", "purpose", "dataset"),
                extra_keys=("category", "prompt", "purpose", "dataset", "expires_at"),
            )
            for index, record in enumerate(categories, start=1)
        ],
        "exception_rationale": section(
            hints,
            ("exception_rationale", "rationale", "justification"),
            "PRJ",
            "business_owner",
            "Document prompt redaction exception rationale",
            evidence_ids,
            ["specific business or safety need that default prompt redaction blocks"],
        ),
        "scope_limits": section(
            hints,
            ("scope_limits", "limits", "redaction_controls", "controls"),
            "PRS",
            "privacy_owner",
            "Constrain prompt redaction exception scope",
            evidence_ids,
            ["time-boxed prompt category, environment, tenant, and data-class limits"],
        ),
        "monitoring": section(
            hints,
            ("monitoring", "monitors"),
            "PRM",
            "compliance_owner",
            "Monitor prompt redaction exception",
            evidence_ids,
            ["redaction bypass volume, sensitive prompt drift, access activity, and incident triggers"],
        ),
        "access_review": section(
            hints,
            ("access_review", "reviewers", "access_reviewers"),
            "PRA",
            "security_owner",
            "Review prompt exception access",
            evidence_ids,
            ["privacy, security, model owner, and support owner access review"],
        ),
        "rollback_criteria": section(
            hints,
            ("rollback_criteria", "rollback", "rollback_triggers"),
            "PRR",
            "privacy_owner",
            "Define prompt redaction exception rollback",
            evidence_ids,
            ["restore default redaction on expiry, sensitive data drift, policy breach, or reviewer rejection"],
        ),
        "evidence_references": ctx["evidence_references"],
    }
