"""Generate deterministic prompt template deprecation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.prompt_template_deprecation_plan.v1"
KIND = "max.spec.prompt_template_deprecation_plan"


def generate_prompt_template_deprecation_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "prompt_template_deprecation")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    templates = unique_records(
        named(
            hints.get("deprecated_templates")
            or hints.get("templates")
            or hints.get("template_inventory"),
            ("template", "template_id", "name"),
        ),
        [
            {
                "name": "deprecated prompt template",
                "template_id": "template-id-required",
                "owner": "prompt_owner",
                "severity": "medium",
            }
        ],
    )
    replacements = unique_records(
        named(
            hints.get("replacement_mapping")
            or hints.get("replacements")
            or hints.get("replacement_templates"),
            ("replacement", "replacement_template", "template_id"),
        ),
        [],
    )
    blockers = _blockers(templates, replacements, evidence_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(
            ctx,
            deprecated_template_count=len(templates),
            blocker_count=len(blockers),
        ),
        "deprecated_templates": [
            item(
                "PTD",
                index,
                record,
                "prompt_owner",
                evidence_ids,
                "Inventory deprecated prompt template",
                name_keys=("name", "template", "template_id", "id"),
                extra_keys=("template", "template_id", "surface", "version", "status"),
            )
            for index, record in enumerate(templates, start=1)
        ],
        "replacement_mapping": [
            item(
                "PTR",
                index,
                record,
                "prompt_owner",
                evidence_ids,
                "Map deprecated prompt template to replacement",
                name_keys=(
                    "name",
                    "template",
                    "replacement",
                    "replacement_template",
                    "template_id",
                ),
                extra_keys=(
                    "template",
                    "template_id",
                    "replacement",
                    "replacement_template",
                    "target_version",
                ),
            )
            for index, record in enumerate(replacements, start=1)
        ],
        "compatibility_checks": section(
            hints,
            ("compatibility_checks", "compatibility", "checks"),
            "PTC",
            "application_owner",
            "Check prompt template compatibility",
            evidence_ids,
            [
                "input variables, output schema, tool calls, safety policy hooks, and downstream parser compatibility"
            ],
        ),
        "rollout_phases": section(
            hints,
            ("rollout_phases", "rollout", "phases"),
            "PTP",
            "release_owner",
            "Roll out prompt template deprecation",
            evidence_ids,
            [
                "shadow comparison, canary traffic, staged migration, default switch, and removal window"
            ],
            extra_keys=("phase", "traffic", "deadline"),
        ),
        "rollback_criteria": section(
            hints,
            ("rollback_criteria", "rollback", "rollback_plan"),
            "PTB",
            "release_owner",
            "Define prompt template rollback criteria",
            evidence_ids,
            [
                "quality regression, safety regression, parser failures, latency increase, or customer escalation"
            ],
        ),
        "evaluation_gates": section(
            hints,
            ("evaluation_gates", "evaluation", "validation_gates"),
            "PTE",
            "evaluation_owner",
            "Gate prompt template deprecation with evaluation",
            evidence_ids,
            [
                "quality comparison against deprecated template, safety pass rate, task success, "
                "latency budget, and reviewer signoff"
            ],
            extra_keys=("metric", "threshold", "baseline", "target"),
        ),
        "audit_evidence": section(
            hints,
            ("audit_evidence", "evidence", "audit"),
            "PTA",
            "compliance_owner",
            "Collect prompt template deprecation audit evidence",
            evidence_ids,
            [
                "template inventory diff, replacement approval, evaluation report, rollout log, and rollback decision log"
            ],
        ),
        "blockers": blockers,
        "evidence_references": ctx["evidence_references"],
    }


def _blockers(
    templates: list[dict[str, Any]], replacements: list[dict[str, Any]], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    replacement_keys = {
        compact(
            record.get("template") or record.get("template_id") or record.get("deprecated_template")
        ).casefold()
        for record in replacements
    }
    has_general_replacement = any(
        compact(record.get("replacement") or record.get("replacement_template"))
        for record in replacements
    )
    blockers: list[dict[str, Any]] = []
    for record in templates:
        template_key = compact(
            record.get("template") or record.get("template_id") or record.get("name")
        ).casefold()
        replacement = compact(record.get("replacement") or record.get("replacement_template"))
        if not replacement and template_key not in replacement_keys and not has_general_replacement:
            blockers.append(
                item(
                    "PTK",
                    len(blockers) + 1,
                    {
                        "name": f"missing replacement for {compact(record.get('name')) or 'deprecated template'}",
                        "template_id": compact(record.get("template_id")),
                        "severity": "high",
                    },
                    "prompt_owner",
                    evidence_ids,
                    "Resolve prompt template deprecation blocker",
                    extra_keys=("template_id",),
                )
            )
    return blockers
