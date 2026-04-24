"""Concise product brief export for one buildable idea."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from max.server.evidence_chain import build_evidence_chain_graph
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


PRODUCT_BRIEF_SCHEMA_VERSION = "max-product-brief/v1"


def generate_idea_product_brief(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    store: Store,
    *,
    include_evidence: bool = True,
    include_validation: bool = True,
) -> dict[str, Any]:
    """Build a compact Markdown product brief and source trace IDs."""
    evidence_chain = _evidence_chain_summary(unit, store) if include_evidence else None
    review_gate = _review_gate_summary(unit.id, store)
    validation_experiments = (
        store.list_validation_experiments(unit.id) or [] if include_validation else []
    )
    source_ids = _source_ids(
        unit,
        evaluation,
        evidence_chain=evidence_chain,
        review_gate=review_gate,
        validation_experiments=validation_experiments,
        include_evidence=include_evidence,
        include_validation=include_validation,
    )
    markdown = render_idea_product_brief_markdown(
        unit,
        evaluation,
        evidence_chain=evidence_chain,
        review_gate=review_gate,
        validation_experiments=validation_experiments,
        include_evidence=include_evidence,
        include_validation=include_validation,
    )
    return {
        "schema_version": PRODUCT_BRIEF_SCHEMA_VERSION,
        "kind": "max.idea_product_brief",
        "idea_id": unit.id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "markdown": markdown,
        "source_ids": source_ids,
    }


def render_idea_product_brief_markdown(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    *,
    evidence_chain: dict[str, Any] | None = None,
    review_gate: dict[str, Any] | None = None,
    validation_experiments: list[dict[str, Any]] | None = None,
    include_evidence: bool = True,
    include_validation: bool = True,
) -> str:
    """Render a product-review-sized Markdown brief with stable headings."""
    lines = [
        f"# {unit.title} Product Brief",
        "",
        f"- Idea ID: {unit.id}",
        f"- Category: {_text(unit.category) or 'unspecified'}",
        f"- Domain: {_text(unit.domain) or 'unspecified'}",
        f"- Summary: {_text(unit.one_liner) or 'No summary provided.'}",
        "",
    ]
    lines.extend(_section("Problem", [_fallback(unit.problem, "No problem statement provided.")]))
    lines.extend(
        _section(
            "Target User and Buyer",
            [
                f"Target users: {_fallback(unit.target_users, 'unspecified')}",
                f"Specific user: {_fallback(unit.specific_user, 'unspecified')}",
                f"Buyer: {_fallback(unit.buyer, 'unspecified')}",
                f"Workflow context: {_fallback(unit.workflow_context, 'unspecified')}",
                f"First customers: {_fallback(unit.first_10_customers, 'unspecified')}",
            ],
        )
    )
    lines.extend(
        _section(
            "Current Workaround",
            [_fallback(unit.current_workaround, "No current workaround captured.")],
        )
    )
    lines.extend(
        _section(
            "Solution",
            [
                _fallback(unit.solution, "No solution statement provided."),
                f"Value proposition: {_fallback(unit.value_proposition, 'unspecified')}",
                f"Technical approach: {_fallback(unit.tech_approach, 'unspecified')}",
                f"Suggested stack: {_stack_summary(unit.suggested_stack)}",
            ],
        )
    )
    lines.extend(_section("Why Now", [_fallback(unit.why_now, "No timing rationale captured.")]))
    if include_evidence:
        lines.extend(_section("Evidence", _evidence_lines(unit, evidence_chain)))
    lines.extend(_section("Evaluation", _evaluation_lines(unit, evaluation, review_gate)))
    lines.extend(_section("Risks", _risks_lines(unit, evaluation, review_gate)))
    if include_validation:
        lines.extend(
            _section(
                "Validation Plan",
                _validation_lines(unit, validation_experiments or []),
            )
        )
    lines.extend(_section("First Milestones", _milestone_lines(unit)))
    return "\n".join(lines).rstrip() + "\n"


def _evidence_chain_summary(unit: BuildableUnit, store: Store) -> dict[str, Any]:
    graph = build_evidence_chain_graph(unit, store)
    return {
        "insight_ids": [item["id"] for item in graph["insights"]],
        "signal_ids": [item["id"] for item in graph["signals"]],
        "insight_count": len(graph["insights"]),
        "signal_count": len(graph["signals"]),
        "edge_count": len(graph["edges"]),
    }


def _review_gate_summary(idea_id: str, store: Store) -> dict[str, Any] | None:
    from max.analysis.review_gate import build_review_gate_decision

    try:
        gate = asdict(build_review_gate_decision(store, idea_id))
    except ValueError:
        return None
    return {
        "decision": gate["decision"],
        "confidence": gate["confidence"],
        "blocking_reasons": gate["blocking_reasons"],
        "warnings": gate["warnings"],
        "required_remediations": gate["required_remediations"],
        "evidence_used": gate["evidence_used"],
    }


def _source_ids(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    *,
    evidence_chain: dict[str, Any] | None,
    review_gate: dict[str, Any] | None,
    validation_experiments: list[dict[str, Any]],
    include_evidence: bool,
    include_validation: bool,
) -> dict[str, list[str]]:
    source_ids = {
        "idea_ids": _dedupe([unit.id, *unit.source_idea_ids]),
        "evaluation_ids": [evaluation.buildable_unit_id] if evaluation else [],
        "insight_ids": [],
        "signal_ids": [],
        "review_gate_sources": [],
        "validation_experiment_ids": [],
    }
    if include_evidence:
        source_ids["insight_ids"] = _dedupe(
            [*unit.inspiring_insights, *(evidence_chain or {}).get("insight_ids", [])]
        )
        source_ids["signal_ids"] = _dedupe(
            [*unit.evidence_signals, *(evidence_chain or {}).get("signal_ids", [])]
        )
    if review_gate:
        source_ids["review_gate_sources"] = _dedupe(
            [str(item.get("source", "")) for item in review_gate.get("evidence_used", [])]
        )
    if include_validation:
        source_ids["validation_experiment_ids"] = _dedupe(
            [str(experiment.get("id", "")) for experiment in validation_experiments]
        )
    return source_ids


def _evidence_lines(unit: BuildableUnit, evidence_chain: dict[str, Any] | None) -> list[str]:
    chain = evidence_chain or {}
    lines = [
        _fallback(unit.evidence_rationale, "No evidence rationale captured."),
        (
            f"Evidence chain: {int(chain.get('insight_count') or 0)} insight(s), "
            f"{int(chain.get('signal_count') or 0)} signal(s), "
            f"{int(chain.get('edge_count') or 0)} relationship(s)."
        ),
        f"Insight IDs: {', '.join(chain.get('insight_ids') or unit.inspiring_insights) or 'none'}",
        f"Signal IDs: {', '.join(chain.get('signal_ids') or unit.evidence_signals) or 'none'}",
    ]
    if unit.source_idea_ids:
        lines.append(f"Source idea IDs: {', '.join(unit.source_idea_ids)}")
    return lines


def _evaluation_lines(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    review_gate: dict[str, Any] | None,
) -> list[str]:
    lines = [
        f"Idea quality score: {unit.quality_score:.1f}",
        f"Novelty score: {unit.novelty_score:.1f}",
        f"Usefulness score: {unit.usefulness_score:.1f}",
    ]
    if evaluation is None:
        lines.append("Utility evaluation: missing.")
    else:
        lines.extend(
            [
                f"Utility score: {evaluation.overall_score:.1f}",
                f"Recommendation: {_fallback(evaluation.recommendation, 'unspecified')}",
                f"Strengths: {', '.join(evaluation.strengths) or 'none'}",
                f"Weaknesses: {', '.join(evaluation.weaknesses) or 'none'}",
            ]
        )
    if review_gate:
        lines.extend(
            [
                f"Review gate: {review_gate['decision']} ({float(review_gate['confidence']):.2f} confidence)",
                f"Gate warnings: {', '.join(review_gate['warnings']) or 'none'}",
            ]
        )
    else:
        lines.append("Review gate: unavailable.")
    return lines


def _risks_lines(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    review_gate: dict[str, Any] | None,
) -> list[str]:
    risks = list(unit.domain_risks)
    if evaluation:
        risks.extend(evaluation.weaknesses)
    if review_gate:
        risks.extend(review_gate.get("blocking_reasons", []))
    return _bullets(_dedupe(risks), empty="No explicit risks captured.")


def _validation_lines(
    unit: BuildableUnit,
    validation_experiments: list[dict[str, Any]],
) -> list[str]:
    lines = [_fallback(unit.validation_plan, "No validation plan captured.")]
    if not validation_experiments:
        lines.append("Validation experiments: none recorded.")
        return lines

    lines.append("Validation experiments:")
    for experiment in validation_experiments[:5]:
        status = _fallback(experiment.get("status"), "unspecified")
        metric = _fallback(experiment.get("success_metric"), "unspecified success metric")
        result = _text(experiment.get("result_summary"))
        summary = (
            f"{experiment.get('id')} [{status}]: "
            f"{_fallback(experiment.get('hypothesis'), 'Untitled hypothesis')} via "
            f"{_fallback(experiment.get('method'), 'unspecified method')}; success metric: {metric}"
        )
        if result:
            summary += f"; result: {result}"
        lines.append(f"- {summary}")
    return lines


def _milestone_lines(unit: BuildableUnit) -> list[str]:
    milestones = [
        f"Frame the first pilot around: {_fallback(unit.specific_user or unit.target_users, 'the target user')}.",
        f"Ship a narrow workflow for: {_fallback(unit.workflow_context, unit.problem)}.",
        f"Validate value proposition: {_fallback(unit.value_proposition, 'the promised outcome')}.",
    ]
    if unit.tech_approach:
        milestones.insert(1, f"Prototype using: {_text(unit.tech_approach)}.")
    if unit.composability_notes:
        milestones.append(f"Preserve composability: {_text(unit.composability_notes)}.")
    return _bullets(milestones)


def _section(title: str, body: list[str]) -> list[str]:
    return [f"## {title}", "", *body, ""]


def _bullets(items: list[Any], *, empty: str | None = None) -> list[str]:
    values = [f"- {_text(item)}" for item in items if _text(item)]
    if values:
        return values
    return [empty] if empty else []


def _stack_summary(stack: dict[str, Any]) -> str:
    if not stack:
        return "unspecified"
    return ", ".join(f"{key}: {value}" for key, value in sorted(stack.items()))


def _fallback(value: Any, fallback: str) -> str:
    return _text(value) or fallback


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _dedupe(values: list[str]) -> list[str]:
    return [value for value in dict.fromkeys(_text(value) for value in values) if value]
