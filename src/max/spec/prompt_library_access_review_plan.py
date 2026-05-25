"""Generate deterministic prompt library access review plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.prompt_library_access_review_plan.v1"
KIND = "max.spec.prompt_library_access_review_plan"


def generate_prompt_library_access_review_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "prompt_library_access_review")
    subjects = unique_records(
        named(hints.get("access_subjects") or hints.get("subjects") or hints.get("users"), ("subject", "user", "group")),
        [{"name": "prompt library users", "permission": "read", "scope": "shared prompt templates"}],
    )
    risks = list(hints.get("risks") or [])
    revocations = list(hints.get("revocation_actions") or hints.get("revocations") or [])
    for record in subjects:
        text = str(record).lower()
        if "stale" in text or "inactive" in text:
            risks.append({"name": "stale prompt library access", "severity": "high"})
            revocations.append("remove stale or inactive prompt library subject access")
        if "write" in text and ("all" in text or "broad" in text or "admin" in text):
            risks.append({"name": "broad prompt library write access", "severity": "high"})
            revocations.append("reduce broad write access to least-privilege maintainers")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, subject_count=len(subjects)),
        "access_subjects": [
            item(
                "PLA",
                index,
                record,
                "prompt_library_owner",
                evidence_ids,
                "Review prompt library access subject",
                name_keys=("name", "subject", "user", "group"),
                extra_keys=("subject", "user", "group", "permission", "scope", "last_used"),
            )
            for index, record in enumerate(subjects, start=1)
        ],
        "permission_levels": section(
            hints,
            ("permission_levels", "permissions", "levels"),
            "PLP",
            "prompt_library_owner",
            "Define prompt library permission level",
            evidence_ids,
            ["read, comment, propose, approve, write, publish, and admin permission levels"],
        ),
        "sensitive_prompt_categories": section(
            hints,
            ("sensitive_prompt_categories", "sensitive_categories", "categories"),
            "PLS",
            "security_owner",
            "Classify sensitive prompt category",
            evidence_ids,
            ["system prompts, safety prompts, regulated workflows, customer-specific templates, and jailbreak defenses"],
        ),
        "review_cadence": section(
            hints,
            ("review_cadence", "cadence", "schedule"),
            "PLC",
            "program_owner",
            "Schedule prompt library access review",
            evidence_ids,
            ["quarterly access review and immediate review after team, role, or sensitive prompt changes"],
        ),
        "revocation_actions": section(
            {"revocation_actions": revocations},
            ("revocation_actions",),
            "PLR",
            "prompt_library_owner",
            "Revoke prompt library access",
            evidence_ids,
            ["remove stale users, downgrade broad write access, and log emergency access expiry"],
        ),
        "evidence": section(
            hints,
            ("evidence", "review_evidence", "audit_evidence"),
            "PLE",
            "compliance_owner",
            "Collect prompt library access evidence",
            evidence_ids,
            ["access export, group membership, last-used report, approval log, and revocation receipt"],
        ),
        "risks": section({"risks": risks}, ("risks",), "PLK", "risk_owner", "Review prompt library access risk", evidence_ids, []),
        "acceptance_criteria": section(
            hints,
            ("acceptance_criteria", "approval_criteria"),
            "PLG",
            "program_owner",
            "Accept prompt library access review",
            evidence_ids,
            ["subjects reviewed, sensitive categories covered, stale access revoked, and evidence attached"],
        ),
        "evidence_references": ctx["evidence_references"],
    }
