"""Generate deterministic evaluation rubric change approval plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.evaluation_rubric_change_approval_plan.v1"
KIND = "max.spec.evaluation_rubric_change_approval_plan"


def generate_evaluation_rubric_change_approval_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "evaluation_rubric_change_approval")
    changes = unique_records(
        named(
            hints.get("changes")
            or hints.get("changed_dimensions")
            or hints.get("rubric_changes")
            or hints.get("dimensions"),
            ("dimension", "rule", "threshold", "weight"),
        ),
        [
            {
                "name": "evaluation rubric change",
                "dimension": "quality scoring",
                "old_value": "current approved rubric",
                "new_value": "proposed rubric update",
                "severity": "medium",
            }
        ],
    )
    validation = section(
        hints,
        ("validation_evidence", "validation", "evidence"),
        "ERV",
        "evaluation_owner",
        "Validate evaluation rubric change",
        evidence_ids,
        ["regression comparison, adjudicated sample, score distribution check, and launch guardrail"],
    )
    risks = section(
        {"risks": _risks(hints, validation)},
        ("risks",),
        "ERR",
        "risk_owner",
        "Review evaluation rubric change risk",
        evidence_ids,
        [],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, change_count=len(changes)),
        "change_summary": [
            item(
                "ERC",
                index,
                record,
                "evaluation_owner",
                evidence_ids,
                "Approve evaluation rubric change",
                name_keys=("name", "dimension", "rule", "threshold", "weight"),
                extra_keys=(
                    "dimension",
                    "rule",
                    "old_value",
                    "new_value",
                    "old_weight",
                    "new_weight",
                    "old_threshold",
                    "new_threshold",
                ),
            )
            for index, record in enumerate(changes, start=1)
        ],
        "impacted_profiles": section(
            hints,
            ("impacted_profiles", "profiles", "segments"),
            "ERP",
            "product_owner",
            "Assess impacted evaluation profile",
            evidence_ids,
            ["all profiles using changed dimensions, weights, thresholds, or recommendation rules"],
            name_keys=("name", "profile", "segment", "persona"),
            extra_keys=("profile", "segment", "persona", "impact"),
        ),
        "validation_evidence": validation,
        "reviewer_roles": section(
            hints,
            ("reviewer_roles", "reviewers", "approvers"),
            "ERRV",
            "program_owner",
            "Require evaluation rubric change reviewer",
            evidence_ids,
            ["evaluation owner, model owner, product owner, responsible AI reviewer, and compliance owner"],
            name_keys=("name", "role", "reviewer"),
            extra_keys=("role", "reviewer", "required"),
        ),
        "rollback_plan": section(
            hints,
            ("rollback_plan", "rollback", "rollback_steps"),
            "ERB",
            "release_manager",
            "Prepare evaluation rubric rollback",
            evidence_ids,
            ["restore prior rubric version, recompute affected scores, and reissue recommendations if needed"],
        ),
        "acceptance_criteria": section(
            hints,
            ("acceptance_criteria", "approval_criteria", "release_gate"),
            "ERA",
            "program_owner",
            "Gate evaluation rubric change approval",
            evidence_ids,
            ["approval captured, regression comparison accepted, and rollback readiness confirmed"],
        ),
        "risks": risks,
        "evidence_references": ctx["evidence_references"],
    }


def _risks(hints: dict[str, Any], validation: list[dict[str, Any]]) -> list[Any]:
    risks = list(hints.get("risks") or hints.get("warnings") or [])
    if not any(key in hints for key in ("validation_evidence", "validation", "evidence")):
        risks.append(
            {
                "name": "missing validation evidence",
                "severity": "high",
                "description": (
                    "Rubric approval is blocked until regression comparison and validation evidence are attached."
                ),
            }
        )
    elif not validation:
        risks.append({"name": "empty validation evidence", "severity": "high"})
    return risks
