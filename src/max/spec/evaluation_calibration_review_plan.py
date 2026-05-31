"""Generate deterministic evaluation calibration review plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, number, string_list, summary

SCHEMA_VERSION = "max.spec.evaluation_calibration_review_plan.v1"
KIND = "max.spec.evaluation_calibration_review_plan"


def generate_evaluation_calibration_review_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    dimensions = _dimensions(hints.get("dimensions") or spec.get("dimensions"))
    examples = _examples(hints.get("examples") or spec.get("examples"))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, dimension_count=len(dimensions), example_count=len(examples), recommendation_count=len([d for d in dimensions if d["recommendation"] != "hold"])),
        "sampling_strategy": _sampling_strategy(examples),
        "dimension_reviews": dimensions,
        "reviewer_protocol": _reviewer_protocol(),
        "disagreement_resolution": _disagreement_resolution(),
        "adoption_metrics": _adoption_metrics(),
        "evidence_references": ctx["evidence_references"],
    }


def _dimensions(value: Any) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else []
    names = raw or ["correctness", "evidence_quality", "implementation_risk"]
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(names, start=1):
        record = item if isinstance(item, dict) else {"name": item}
        name = compact(record.get("name") or record.get("dimension")) or f"dimension_{index}"
        approvals = int(number(record.get("approvals")) or 0)
        rejections = int(number(record.get("rejections")) or 0)
        golden = int(number(record.get("golden_examples")) or 0)
        disagreement = float(number(record.get("disagreement_rate")) or 0.0)
        rows.append(
            {
                "id": f"ECD{index}",
                "name": name,
                "approvals": approvals,
                "rejections": rejections,
                "golden_examples": golden,
                "disagreement_rate": disagreement,
                "recommendation": _recommendation(approvals, rejections, golden, disagreement),
                "review_action": _review_action(name, approvals, rejections, golden, disagreement),
            }
        )
    return sorted(rows, key=lambda row: (_recommendation_rank(row["recommendation"]), row["name"].casefold()))


def _examples(value: Any) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    for index, item in enumerate(value if isinstance(value, list) else [], start=1):
        if isinstance(item, dict):
            examples.append({"id": compact(item.get("id")) or f"EX{index}", "outcome": compact(item.get("outcome")) or "unclassified", "dimension": compact(item.get("dimension")) or "all"})
    return sorted(examples, key=lambda item: (item["dimension"].casefold(), item["id"].casefold()))


def _sampling_strategy(examples: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        {"id": "ECS1", "name": "recent_approvals", "target": "sample recent approvals by profile and dimension", "available_examples": _count(examples, "approve")},
        {"id": "ECS2", "name": "recent_rejections", "target": "sample recent rejections by failure mode", "available_examples": _count(examples, "reject")},
        {"id": "ECS3", "name": "golden_examples", "target": "include stable golden examples for every configured dimension", "available_examples": _count(examples, "golden")},
    ]


def _reviewer_protocol() -> list[dict[str, str]]:
    return [
        {"id": "ECP1", "name": "blind_rescore", "description": "Reviewers rescore sampled examples without seeing prior labels."},
        {"id": "ECP2", "name": "dimension_notes", "description": "Capture rationale for every changed dimension score."},
        {"id": "ECP3", "name": "calibration_summary", "description": "Publish proposed threshold and rubric changes before adoption."},
    ]


def _disagreement_resolution() -> list[dict[str, str]]:
    return [
        {"id": "ECR1", "name": "adjudication", "description": "Escalate reviewer disagreements to evaluation owner adjudication."},
        {"id": "ECR2", "name": "rubric_update", "description": "Update rubric language when disagreement repeats for the same dimension."},
    ]


def _adoption_metrics() -> list[dict[str, str]]:
    return [
        {"id": "ECM1", "name": "reviewer_agreement_rate", "target": ">= 80% after recalibration"},
        {"id": "ECM2", "name": "golden_example_pass_rate", "target": ">= 95%"},
        {"id": "ECM3", "name": "approval_reversal_rate", "target": "within agreed tolerance"},
    ]


def _recommendation(approvals: int, rejections: int, golden: int, disagreement: float) -> str:
    if golden == 0 or disagreement >= 0.25:
        return "recalibrate"
    if rejections > approvals:
        return "tighten"
    return "hold"


def _review_action(name: str, approvals: int, rejections: int, golden: int, disagreement: float) -> str:
    if golden == 0:
        return f"Add golden examples before adopting {name} threshold changes."
    if disagreement >= 0.25:
        return f"Run reviewer calibration workshop for {name}."
    if rejections > approvals:
        return f"Tighten {name} scoring guidance using recent rejection examples."
    return f"Keep {name} thresholds and monitor drift."


def _recommendation_rank(value: str) -> int:
    return {"recalibrate": 0, "tighten": 1, "hold": 2}.get(value, 3)


def _count(examples: list[dict[str, str]], outcome: str) -> int:
    return sum(1 for item in examples if item["outcome"].casefold() == outcome)


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("evaluation_calibration_review")
    return hints if isinstance(hints, dict) else {}
