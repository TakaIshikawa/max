"""Generate deterministic model evaluation holdout plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.model_evaluation_holdout_plan.v1"
KIND = "max.spec.model_evaluation_holdout_plan"


def generate_model_evaluation_holdout_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "model_evaluation_holdout")
    holdouts = unique_records(
        named(
            hints.get("holdout_datasets") or hints.get("datasets") or hints.get("holdouts"),
            ("dataset", "source", "cadence"),
        ),
        [
            {
                "name": "golden holdout dataset",
                "dataset": "golden holdout dataset",
                "owner": "evaluation_owner",
                "cadence": "monthly",
                "severity": "medium",
            }
        ],
    )
    dimensions = unique_records(
        named(
            hints.get("evaluation_dimensions") or hints.get("dimensions") or hints.get("metrics"),
            ("dimension", "metric", "threshold"),
        ),
        [
            {
                "name": "quality and safety regression",
                "dimension": "quality",
                "threshold": "no material regression",
            }
        ],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(
            ctx,
            holdout_dataset_count=len(holdouts),
            dimension_count=len(dimensions),
        ),
        "holdout_datasets": [
            item(
                "MEH",
                index,
                record,
                "evaluation_owner",
                evidence_ids,
                "Maintain model evaluation holdout dataset",
                name_keys=("name", "dataset", "source"),
                extra_keys=("dataset", "source", "cadence"),
            )
            for index, record in enumerate(holdouts, start=1)
        ],
        "evaluation_dimensions": [
            item(
                "MED",
                index,
                record,
                "evaluation_owner",
                evidence_ids,
                "Evaluate holdout dimension",
                name_keys=("name", "dimension", "metric"),
                extra_keys=("dimension", "metric", "threshold", "cadence"),
            )
            for index, record in enumerate(dimensions, start=1)
        ],
        "leakage_controls": section(
            hints,
            ("leakage_controls", "leakage", "controls"),
            "MEL",
            "data_governance_owner",
            "Control holdout leakage",
            evidence_ids,
            [
                "segregate holdout storage, deny training access, hash membership checks, "
                "and audit prompt exposure"
            ],
        ),
        "refresh_cadence": section(
            hints,
            ("refresh_cadence", "cadence", "refresh"),
            "MER",
            "evaluation_owner",
            "Refresh holdout dataset",
            evidence_ids,
            [
                "monthly review with versioned additions, drift sampling, and retired "
                "examples retained for audit"
            ],
            extra_keys=("cadence",),
        ),
        "access_review": section(
            hints,
            ("access_review", "access_reviewers", "reviewers"),
            "MEA",
            "security_owner",
            "Review holdout access",
            evidence_ids,
            [
                "model owner, evaluation owner, security reviewer, and privacy reviewer "
                "access recertification"
            ],
        ),
        "pass_fail_thresholds": section(
            hints,
            ("pass_fail_thresholds", "thresholds", "gates"),
            "MET",
            "quality_owner",
            "Set holdout pass fail threshold",
            evidence_ids,
            [
                "quality above baseline, safety failures at zero criticals, and no "
                "protected-segment regression"
            ],
            extra_keys=("dimension", "metric", "threshold", "cadence"),
        ),
        "reporting_plan": section(
            hints,
            ("reporting_plan", "reporting", "reports"),
            "MEP",
            "program_owner",
            "Report holdout evaluation results",
            evidence_ids,
            ["release gate report, failure analysis, threshold waiver log, and evidence bundle"],
        ),
        "evidence_references": ctx["evidence_references"],
    }
