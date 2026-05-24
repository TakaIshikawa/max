"""Generate deterministic retrospective learning holdout plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.retrospective_learning_holdout_plan.v1"
KIND = "max.spec.retrospective_learning_holdout_plan"
DEFAULT_HOLDOUT_PERCENTAGE = 10


def generate_retrospective_learning_holdout_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "retrospective_learning_holdout")
    holdout_percentage = _percentage(
        hints.get("holdout_percentage")
        or hints.get("percentage")
        or hints.get("holdout_percent")
        or DEFAULT_HOLDOUT_PERCENTAGE
    )
    cohorts = unique_records(
        named(hints.get("cohorts") or hints.get("holdout_cohorts") or hints.get("profiles"), ("cohort", "profile", "segment")),
        [
            {
                "name": "retrospective feedback holdout",
                "cohort": "retrospective feedback holdout",
                "owner": "learning_owner",
            }
        ],
    )
    metrics = unique_records(
        named(hints.get("metrics") or hints.get("success_metrics") or hints.get("measures"), ("metric", "measure", "threshold")),
        [{"name": "held-out outcome prediction quality", "metric": "held-out outcome prediction quality"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(
            ctx,
            holdout_percentage=holdout_percentage,
            cohort_count=len(cohorts),
            metric_count=len(metrics),
        ),
        "holdout_cohorts": [
            item(
                "RLH",
                index,
                {**record, "holdout_percentage": str(holdout_percentage)},
                "learning_owner",
                evidence_ids,
                "Define retrospective learning holdout cohort",
                name_keys=("name", "cohort", "profile", "segment"),
                extra_keys=("cohort", "profile", "segment", "holdout_percentage", "duration"),
            )
            for index, record in enumerate(cohorts, start=1)
        ],
        "timeline": section(
            hints,
            ("timeline", "duration", "schedule"),
            "RLT",
            "program_owner",
            "Run retrospective learning holdout timeline",
            evidence_ids,
            ["hold back feedback outcomes for 30 days or one learning release cycle before analysis"],
            extra_keys=("duration", "start", "end"),
        ),
        "success_metrics": [
            item(
                "RLM",
                index,
                record,
                "learning_owner",
                evidence_ids,
                "Measure retrospective learning holdout success",
                name_keys=("name", "metric", "measure"),
                extra_keys=("metric", "measure", "threshold", "baseline"),
            )
            for index, record in enumerate(metrics, start=1)
        ],
        "guardrails": section(
            hints,
            ("guardrails", "controls"),
            "RLG",
            "safety_owner",
            "Apply retrospective learning guardrail",
            evidence_ids,
            [
                "do not learn from held-out outcomes, protected segments, unresolved conflicts, "
                "or safety-escalated feedback"
            ],
        ),
        "analysis_steps": section(
            hints,
            ("analysis_steps", "analysis", "review_steps"),
            "RLA",
            "analytics_owner",
            "Analyze retrospective learning holdout",
            evidence_ids,
            [
                "compare learned scoring changes against held-out outcomes, cohort drift, "
                "and regression thresholds"
            ],
        ),
        "reintegration_criteria": section(
            hints,
            ("reintegration_criteria", "reintegration", "release_criteria"),
            "RLR",
            "learning_owner",
            "Gate holdout reintegration",
            evidence_ids,
            ["reintegrate only after success metrics pass, guardrails hold, and reviewer signoff is captured"],
        ),
        "evidence_references": ctx["evidence_references"],
    }


def _percentage(value: Any) -> int:
    text = compact(value).rstrip("%")
    try:
        number = float(text)
    except ValueError:
        number = DEFAULT_HOLDOUT_PERCENTAGE
    if 0 < number <= 1:
        number *= 100
    return max(1, min(50, round(number)))
