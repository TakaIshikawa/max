"""Generate deterministic prompt injection incident response plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.prompt_injection_incident_response_plan.v1"
KIND = "max.spec.prompt_injection_incident_response_plan"


def generate_prompt_injection_incident_response_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "prompt_injection_incident_response")
    affected_sources = unique_records(
        named(
            hints.get("affected_sources") or hints.get("source_ids") or hints.get("sources"),
            ("source_id", "source", "id"),
        ),
        [{"name": "suspected source signal", "source_id": "unknown_source", "owner": "source_owner"}],
    )
    affected_prompts = unique_records(
        named(
            hints.get("affected_prompts") or hints.get("prompt_ids") or hints.get("prompts"),
            ("prompt_id", "prompt", "id"),
        ),
        [{"name": "suspected generated spec prompt", "prompt_id": "unknown_prompt", "owner": "prompt_owner"}],
    )
    reviewer_roles = unique_records(
        named(hints.get("reviewer_roles") or hints.get("reviewers") or hints.get("roles"), ("role", "reviewer", "owner")),
        [
            {"name": "security reviewer", "role": "security reviewer", "owner": "security_owner"},
            {"name": "prompt owner", "role": "prompt owner", "owner": "prompt_owner"},
        ],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(
            ctx,
            affected_source_count=len(affected_sources),
            affected_prompt_count=len(affected_prompts),
            reviewer_role_count=len(reviewer_roles),
        ),
        "detection_summary": section(
            hints,
            ("detection_summary", "detection", "signals"),
            "PID",
            "security_owner",
            "Summarize prompt injection detection",
            evidence_ids,
            ["suspected prompt injection in source signals or generated specs"],
            extra_keys=("severity", "detected_at", "detector"),
        ),
        "affected_sources": [
            item(
                "PIS",
                index,
                record,
                "source_owner",
                evidence_ids,
                "Review affected source signal",
                name_keys=("name", "source_id", "source", "id"),
                extra_keys=("source_id", "source", "adapter"),
            )
            for index, record in enumerate(affected_sources, start=1)
        ],
        "affected_prompts": [
            item(
                "PIP",
                index,
                record,
                "prompt_owner",
                evidence_ids,
                "Review affected prompt",
                name_keys=("name", "prompt_id", "prompt", "id"),
                extra_keys=("prompt_id", "prompt", "spec_id"),
            )
            for index, record in enumerate(affected_prompts, start=1)
        ],
        "reviewer_roles": [
            item(
                "PIR",
                index,
                record,
                "security_owner",
                evidence_ids,
                "Assign prompt injection reviewer role",
                name_keys=("name", "role", "reviewer", "owner"),
                extra_keys=("role", "reviewer", "responsibility"),
            )
            for index, record in enumerate(reviewer_roles, start=1)
        ],
        "containment_tasks": section(
            hints,
            ("containment_tasks", "containment", "containment_steps"),
            "PIC",
            "incident_owner",
            "Contain prompt injection incident",
            evidence_ids,
            [
                "quarantine suspect source signals, pause affected spec generation, "
                "and disable automated publication"
            ],
        ),
        "evidence_handling": section(
            hints,
            ("evidence_handling", "evidence_preservation", "evidence"),
            "PIE",
            "security_owner",
            "Preserve prompt injection evidence",
            evidence_ids,
            [
                "snapshot raw source payloads, generated specs, prompts, model responses, "
                "review decisions, and audit logs"
            ],
        ),
        "recovery_steps": section(
            hints,
            ("recovery_steps", "recovery", "remediation"),
            "PIV",
            "prompt_owner",
            "Recover prompt injection workflow",
            evidence_ids,
            [
                "remove injected content, regenerate affected specs from trusted sources, "
                "and require reviewer approval before release"
            ],
        ),
        "communications": section(
            hints,
            ("communications", "comms", "notifications"),
            "PIM",
            "incident_owner",
            "Coordinate prompt injection communication",
            evidence_ids,
            ["notify security, source owners, prompt owners, reviewers, and affected downstream consumers"],
        ),
        "post_incident_controls": section(
            hints,
            ("post_incident_controls", "controls", "followups"),
            "PIF",
            "safety_owner",
            "Strengthen prompt injection control",
            evidence_ids,
            [
                "add source sanitization checks, prompt boundary tests, generated-spec review gates, "
                "and injection regression coverage"
            ],
        ),
        "closure_criteria": section(
            hints,
            ("closure_criteria", "closure", "acceptance_criteria"),
            "PIX",
            "incident_owner",
            "Close prompt injection incident",
            evidence_ids,
            [
                "all affected prompts and sources reviewed, evidence retained, clean specs regenerated, "
                "communications sent, and post-incident controls assigned"
            ],
        ),
        "evidence_references": ctx["evidence_references"],
    }
