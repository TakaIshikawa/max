"""Generate deterministic model bias review plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.model_bias_review_plan.v1"
KIND = "max.spec.model_bias_review_plan"


def generate_model_bias_review_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "model_bias_review")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    cohorts = unique_records(
        named(hints.get("cohorts") or hints.get("profiles") or hints.get("target_users"), ("profile", "segment", "target_user")),
        [
            {
                "name": "representative user cohorts",
                "profile": "representative user cohorts",
                "owner": "evaluation_owner",
                "severity": "medium",
            }
        ],
    )
    metrics = unique_records(
        named(hints.get("metrics") or hints.get("evaluation_dimensions") or hints.get("dimensions"), ("metric", "dimension", "threshold")),
        [
            {
                "name": "protected cohort quality parity",
                "metric": "quality parity",
                "threshold": "no material protected-cohort regression",
            }
        ],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Model Bias Review Plan",
        "summary": source_summary(ctx, cohort_count=len(cohorts), metric_count=len(metrics)),
        "cohorts": [
            item(
                "MBR",
                index,
                record,
                "evaluation_owner",
                evidence_ids,
                "Review model bias cohort",
                name_keys=("name", "profile", "segment", "target_user"),
                extra_keys=("profile", "segment", "target_user", "sample_size"),
            )
            for index, record in enumerate(cohorts, start=1)
        ],
        "bias_hypotheses": section(
            hints,
            ("bias_hypotheses", "hypotheses", "risks"),
            "MBH",
            "responsible_ai_owner",
            "Define model bias hypothesis",
            evidence_ids,
            ["LLM-generated insights may vary in tone, accuracy, safety, or actionability by cohort"],
        ),
        "metrics": [
            item(
                "MBM",
                index,
                record,
                "quality_owner",
                evidence_ids,
                "Measure model bias review metric",
                name_keys=("name", "metric", "dimension"),
                extra_keys=("metric", "dimension", "threshold"),
            )
            for index, record in enumerate(metrics, start=1)
        ],
        "review_rubric": section(
            hints,
            ("review_rubric", "rubric", "reviewer_rubric"),
            "MBU",
            "responsible_ai_owner",
            "Apply model bias reviewer rubric",
            evidence_ids,
            [
                "score factuality, harmful stereotypes, missing context, disparate recommendations, "
                "and reviewer rationale"
            ],
        ),
        "mitigation_actions": section(
            hints,
            ("mitigation_actions", "mitigations", "actions"),
            "MBA",
            "model_owner",
            "Plan model bias mitigation action",
            evidence_ids,
            ["prompt adjustment, retrieval filter, cohort-specific evaluation expansion, or release hold"],
        ),
        "escalation_criteria": section(
            hints,
            ("escalation_criteria", "escalation", "release_hold_criteria"),
            "MBE",
            "program_owner",
            "Escalate model bias review finding",
            evidence_ids,
            ["critical safety finding, statistically material cohort gap, or unresolved reviewer disagreement"],
        ),
        "acceptance_gate": section(
            hints,
            ("acceptance_gate", "acceptance_criteria", "release_gate"),
            "MBG",
            "release_manager",
            "Gate release on model bias review",
            evidence_ids,
            ["all critical findings resolved, parity thresholds met, mitigations tracked, and approvers signed off"],
        ),
        "evidence_references": ctx["evidence_references"],
    }
