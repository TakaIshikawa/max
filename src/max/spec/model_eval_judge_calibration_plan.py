"""Generate deterministic model eval judge calibration plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.model_eval_judge_calibration_plan.v1"
KIND = "max.spec.model_eval_judge_calibration_plan"


def generate_model_eval_judge_calibration_plan(spec_like: Any) -> dict[str, Any]:
    """Return a stable calibration plan for model-based evaluation judges."""
    _spec, ctx, hints, evidence_ids = base(spec_like, "model_eval_judge_calibration")
    gold_examples = unique_records(hints.get("gold_examples") or hints.get("examples"), [])
    reviewers = unique_records(hints.get("reviewers") or hints.get("reviewer_assignments"), [])
    blockers = _blockers(hints, reviewers, evidence_ids)
    warnings = _warnings(gold_examples, hints, evidence_ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, gold_example_count=len(gold_examples), reviewer_count=len(reviewers), blocker_count=len(blockers), warning_count=len(warnings)),
        "rubric_alignment": section(hints, ("rubric_alignment", "rubric"), "MJR", "quality_owner", "Align judge rubric", evidence_ids, ["map rubric dimensions to product policy, safety criteria, and expected reviewer interpretation"]),
        "gold_examples": section(hints, ("gold_examples", "examples"), "MJG", "quality_owner", "Curate judge gold example", evidence_ids, ["passing, failing, borderline, and policy-sensitive examples with expected labels"]),
        "disagreement_thresholds": section(hints, ("disagreement_thresholds", "thresholds"), "MJT", "quality_owner", "Set judge disagreement threshold", evidence_ids, ["human-judge disagreement <= 5 percent and critical disagreement = 0"]),
        "drift_checks": section(hints, ("drift_checks", "drift"), "MJD", "ml_platform_owner", "Check judge calibration drift", evidence_ids, ["weekly score distribution drift and rubric version drift check"]),
        "reviewer_assignments": section(hints, ("reviewers", "reviewer_assignments"), "MJA", "program_owner", "Assign calibration reviewer", evidence_ids, ["primary reviewer, adjudicator, and approver assigned"]),
        "recertification_cadence": section(hints, ("recertification_cadence", "cadence"), "MJC", "program_owner", "Schedule judge recertification", evidence_ids, ["monthly recertification and immediate recertification after rubric or model changes"]),
        "blockers": blockers,
        "warnings": warnings,
        "evidence_references": ctx["evidence_references"],
    }


def _blockers(hints: dict[str, Any], reviewers: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    threshold_text = compact(hints.get("max_disagreement_rate") or hints.get("disagreement_threshold")).lower()
    if threshold_text in {"", "missing", "tbd", "unknown"}:
        blockers.append(row("MJK", 1, "missing disagreement threshold", "quality_owner", "Judge calibration requires a quantified disagreement threshold.", evidence_ids, severity="high"))
    if not reviewers:
        blockers.append(row("MJK", len(blockers) + 1, "missing calibration reviewers", "program_owner", "Judge calibration requires named reviewers or reviewer roles.", evidence_ids, severity="high"))
    return blockers


def _warnings(gold_examples: list[dict[str, Any]], hints: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    minimum = int(hints.get("minimum_gold_examples") or 3)
    if len(gold_examples) < minimum:
        return [row("MJW", 1, "insufficient gold example coverage", "quality_owner", f"Gold example coverage has {len(gold_examples)} examples; expected at least {minimum}.", evidence_ids, severity="medium")]
    return []
