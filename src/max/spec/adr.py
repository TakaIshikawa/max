"""Generate Architecture Decision Records for approved buildable ideas."""

from __future__ import annotations

from typing import Any

from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


ARCHITECTURE_DECISION_RECORD_SCHEMA_VERSION = "max-adr/v1"

DIMENSION_NAMES = (
    "pain_severity",
    "addressable_scale",
    "build_effort",
    "composability",
    "competitive_density",
    "timing_fit",
    "compounding_value",
)


def generate_architecture_decision_record(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    supporting_insights: list[Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic ADR handoff from one buildable idea."""
    evidence_links = _evidence_links(unit, supporting_insights)
    evaluation_summary = _evaluation_summary(evaluation)

    return {
        "schema_version": ARCHITECTURE_DECISION_RECORD_SCHEMA_VERSION,
        "kind": "max.architecture_decision_record",
        "idea_id": unit.id,
        "status": _adr_status(unit, evaluation),
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": unit.id,
            "idea_status": unit.status,
            "domain": unit.domain,
            "category": str(unit.category),
            "evaluation_available": evaluation is not None,
            "supporting_insight_count": len(supporting_insights or []),
        },
        "context": {
            "title": unit.title,
            "one_liner": unit.one_liner,
            "problem": unit.problem,
            "target_user": _target_user(unit),
            "buyer": unit.buyer,
            "workflow_context": unit.workflow_context,
            "current_workaround": unit.current_workaround,
            "why_now": unit.why_now,
            "value_proposition": unit.value_proposition,
        },
        "decision": {
            "summary": _decision_summary(unit),
            "selected_approach": _compact(unit.solution)
            or "Use the proposed solution described by the buildable idea.",
            "technical_approach": _compact(unit.tech_approach) or "Technical approach is not specified yet.",
            "suggested_stack": dict(unit.suggested_stack or {}),
            "composability_notes": _compact(unit.composability_notes)
            or "No composability notes were provided.",
        },
        "considered_alternatives": _considered_alternatives(unit),
        "consequences": {
            "positive": _positive_consequences(unit, evaluation),
            "negative": _negative_consequences(unit, evaluation),
            "follow_up_actions": _follow_up_actions(unit, evaluation),
        },
        "evidence_links": evidence_links,
        "evaluation_summary": evaluation_summary,
    }


def render_architecture_decision_record_markdown(record: dict[str, Any]) -> str:
    """Render a generated ADR as deterministic markdown."""
    context = record.get("context", {})
    decision = record.get("decision", {})
    consequences = record.get("consequences", {})
    evaluation = record.get("evaluation_summary", {})
    source = record.get("source", {})

    lines = [
        f"# ADR: {_text(context.get('title'))}",
        "",
        f"- Schema version: {_text(record.get('schema_version'))}",
        f"- Idea ID: {_text(record.get('idea_id'))}",
        f"- Status: {_text(record.get('status'))}",
        f"- Source idea status: {_text(source.get('idea_status'))}",
        f"- Domain: {_text(source.get('domain'))}",
        f"- Category: {_text(source.get('category'))}",
        "",
        "## Context",
        "",
        f"- One-liner: {_text(context.get('one_liner'))}",
        f"- Problem: {_text(context.get('problem'))}",
        f"- Target user: {_text(context.get('target_user'))}",
        f"- Buyer: {_text(context.get('buyer'))}",
        f"- Workflow context: {_text(context.get('workflow_context'))}",
        f"- Current workaround: {_text(context.get('current_workaround'))}",
        f"- Why now: {_text(context.get('why_now'))}",
        f"- Value proposition: {_text(context.get('value_proposition'))}",
        "",
        "## Decision",
        "",
        f"- Summary: {_text(decision.get('summary'))}",
        f"- Selected approach: {_text(decision.get('selected_approach'))}",
        f"- Technical approach: {_text(decision.get('technical_approach'))}",
        f"- Suggested stack: {_stack_text(decision.get('suggested_stack'))}",
        f"- Composability notes: {_text(decision.get('composability_notes'))}",
        "",
        "## Considered Alternatives",
        "",
    ]

    alternatives = record.get("considered_alternatives") or []
    if alternatives:
        for alternative in alternatives:
            lines.extend(
                [
                    f"### {_text(alternative.get('name'))}",
                    "",
                    f"- Description: {_text(alternative.get('description'))}",
                    f"- Rationale: {_text(alternative.get('rationale'))}",
                    f"- Outcome: {_text(alternative.get('outcome'))}",
                    "",
                ]
            )
    else:
        lines.extend(["No alternatives were captured.", ""])

    lines.extend(
        [
            "## Consequences",
            "",
            "### Positive",
            "",
            *_bullets(consequences.get("positive") or [], empty="No positive consequences captured."),
            "",
            "### Negative",
            "",
            *_bullets(consequences.get("negative") or [], empty="No negative consequences captured."),
            "",
            "### Follow-up Actions",
            "",
            *_bullets(consequences.get("follow_up_actions") or [], empty="No follow-up actions captured."),
            "",
            "## Evidence Links",
            "",
        ]
    )

    evidence_links = record.get("evidence_links") or []
    if evidence_links:
        for link in evidence_links:
            link_type = _text(link.get("type"))
            link_id = _text(link.get("id"))
            summary = _text(link.get("summary"))
            lines.append(f"- {link_type}:{link_id} - {summary}")
    else:
        lines.append("No evidence links were provided.")

    lines.extend(
        [
            "",
            "## Evaluation Summary",
            "",
            f"- Evaluation available: {_text(evaluation.get('available'))}",
            f"- Recommendation: {_text(evaluation.get('recommendation'))}",
            f"- Overall score: {_text(evaluation.get('overall_score'))}",
            f"- Summary: {_text(evaluation.get('summary'))}",
            "- Strengths:",
            *_bullets(evaluation.get("strengths") or [], empty="None."),
            "- Weaknesses:",
            *_bullets(evaluation.get("weaknesses") or [], empty="None."),
            "- Dimension scores:",
            *_dimension_bullets(evaluation.get("dimensions") or []),
            "",
        ]
    )

    return "\n".join(lines).rstrip() + "\n"


def _adr_status(unit: BuildableUnit, evaluation: UtilityEvaluation | None) -> str:
    if evaluation is None:
        return "proposed"
    if unit.status == "approved" and evaluation.recommendation in {"strong_yes", "yes"}:
        return "accepted"
    if evaluation.recommendation in {"no", "strong_no"}:
        return "rejected"
    return "proposed"


def _decision_summary(unit: BuildableUnit) -> str:
    target = _target_user(unit)
    solution = _compact(unit.solution) or unit.title
    return f"Build {unit.title} for {target} using this approach: {solution}"


def _target_user(unit: BuildableUnit) -> str:
    return _compact(unit.specific_user) or _compact(unit.target_users) or "target user"


def _considered_alternatives(unit: BuildableUnit) -> list[dict[str, str]]:
    alternatives = [
        {
            "name": "Build the proposed MVP",
            "description": _compact(unit.solution) or unit.title,
            "rationale": _compact(unit.value_proposition)
            or "The idea describes a direct solution to the stated problem.",
            "outcome": "selected",
        },
        {
            "name": "Do nothing",
            "description": "Leave the workflow unchanged.",
            "rationale": "Avoids implementation effort but leaves the stated problem unresolved.",
            "outcome": "rejected",
        },
    ]

    workaround = _compact(unit.current_workaround)
    if workaround:
        alternatives.append(
            {
                "name": "Continue current workaround",
                "description": workaround,
                "rationale": "Keeps users on the existing path without new product surface area.",
                "outcome": "rejected",
            }
        )

    validation_plan = _compact(unit.validation_plan)
    if validation_plan:
        alternatives.append(
            {
                "name": "Validation-only spike",
                "description": validation_plan,
                "rationale": "Reduces build commitment while collecting implementation evidence.",
                "outcome": "deferred unless ADR risks block the MVP.",
            }
        )

    return alternatives


def _positive_consequences(unit: BuildableUnit, evaluation: UtilityEvaluation | None) -> list[str]:
    consequences = [
        _compact(unit.value_proposition),
        _compact(unit.composability_notes),
    ]
    if evaluation is not None:
        consequences.extend(_compact(strength) for strength in evaluation.strengths)
    return [item for item in consequences if item] or [
        "The selected approach gives the team a concrete implementation target."
    ]


def _negative_consequences(unit: BuildableUnit, evaluation: UtilityEvaluation | None) -> list[str]:
    consequences = [_compact(risk) for risk in unit.domain_risks]
    if evaluation is not None:
        consequences.extend(_compact(weakness) for weakness in evaluation.weaknesses)
    return [item for item in consequences if item] or [
        "No explicit risks or weaknesses were provided; validate assumptions before broad launch."
    ]


def _follow_up_actions(unit: BuildableUnit, evaluation: UtilityEvaluation | None) -> list[str]:
    actions: list[str] = []
    if _compact(unit.validation_plan):
        actions.append(unit.validation_plan)
    if not _compact(unit.tech_approach):
        actions.append("Document the technical approach before implementation starts.")
    if not _compact(unit.workflow_context):
        actions.append("Clarify the workflow context and first user journey.")
    if evaluation is None:
        actions.append("Run a utility evaluation before treating this ADR as final.")
    elif evaluation.recommendation not in {"strong_yes", "yes"}:
        actions.append("Resolve evaluation weaknesses or reduce scope before implementation.")
    return actions or ["Confirm ADR assumptions during implementation planning."]


def _evidence_links(unit: BuildableUnit, supporting_insights: list[Any] | None) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    links.extend(
        {"type": "insight", "id": insight_id, "summary": "Inspiring insight reference."}
        for insight_id in unit.inspiring_insights
        if _compact(insight_id)
    )
    links.extend(
        {"type": "signal", "id": signal_id, "summary": "Evidence signal reference."}
        for signal_id in unit.evidence_signals
        if _compact(signal_id)
    )
    links.extend(
        {"type": "idea", "id": idea_id, "summary": "Source idea reference."}
        for idea_id in unit.source_idea_ids
        if _compact(idea_id)
    )
    links.extend(_supporting_insight_link(insight) for insight in supporting_insights or [])

    deduped: dict[tuple[str, str], dict[str, str]] = {}
    for link in links:
        key = (link["type"], link["id"])
        if key not in deduped:
            deduped[key] = link
    return list(deduped.values())


def _supporting_insight_link(insight: Any) -> dict[str, str]:
    if isinstance(insight, dict):
        insight_id = _compact(insight.get("id")) or _compact(insight.get("title")) or "supporting-insight"
        summary = (
            _compact(insight.get("summary"))
            or _compact(insight.get("title"))
            or "Supporting insight provided at generation time."
        )
        url = _compact(insight.get("url"))
        if url:
            summary = f"{summary} ({url})"
        return {"type": "supporting_insight", "id": insight_id, "summary": summary}

    insight_id = _compact(getattr(insight, "id", "")) or _compact(str(insight)) or "supporting-insight"
    summary = (
        _compact(getattr(insight, "summary", ""))
        or _compact(getattr(insight, "title", ""))
        or _compact(str(insight))
        or "Supporting insight provided at generation time."
    )
    return {"type": "supporting_insight", "id": insight_id, "summary": summary}


def _evaluation_summary(evaluation: UtilityEvaluation | None) -> dict[str, Any]:
    if evaluation is None:
        return {
            "available": False,
            "recommendation": None,
            "overall_score": None,
            "summary": "No utility evaluation was provided.",
            "strengths": [],
            "weaknesses": ["Utility evaluation is missing."],
            "dimensions": [],
        }

    dimensions = []
    for name in DIMENSION_NAMES:
        score = getattr(evaluation, name)
        dimensions.append(
            {
                "name": name,
                "value": score.value,
                "confidence": score.confidence,
                "reasoning": score.reasoning,
            }
        )

    return {
        "available": True,
        "recommendation": evaluation.recommendation,
        "overall_score": evaluation.overall_score,
        "summary": (
            f"Recommendation {evaluation.recommendation} with overall score "
            f"{evaluation.overall_score:.1f}/100."
        ),
        "strengths": [_compact(strength) for strength in evaluation.strengths if _compact(strength)],
        "weaknesses": [_compact(weakness) for weakness in evaluation.weaknesses if _compact(weakness)],
        "dimensions": dimensions,
    }


def _dimension_bullets(dimensions: list[dict[str, Any]]) -> list[str]:
    if not dimensions:
        return ["None."]
    return [
        (
            f"- {dimension['name']}: {dimension['value']:.1f}/10 "
            f"(confidence {dimension['confidence']:.2f}) - {_text(dimension.get('reasoning'))}"
        )
        for dimension in dimensions
    ]


def _stack_text(stack: Any) -> str:
    if not stack:
        return "none"
    if isinstance(stack, dict):
        return ", ".join(f"{key}={value}" for key, value in sorted(stack.items())) or "none"
    return _text(stack)


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    text = _compact(value)
    return text or "none"


def _bullets(values: list[Any], *, empty: str = "None.") -> list[str]:
    items = [f"- {_text(value)}" for value in values if _compact(value)]
    return items or [empty]
