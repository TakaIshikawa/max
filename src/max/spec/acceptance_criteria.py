"""Generate implementation-ready acceptance criteria for buildable ideas."""

from __future__ import annotations

from typing import Any

from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


ACCEPTANCE_CRITERIA_SCHEMA_VERSION = "max-acceptance-criteria/v1"


def generate_acceptance_criteria(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    evidence_density: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn an evaluated idea into deterministic implementation acceptance criteria."""
    functional = _functional_criteria(unit, evaluation)
    non_functional = _non_functional_criteria(unit, evaluation, evidence_density)
    evidence_links = _evidence_links(unit)

    return {
        "schema_version": ACCEPTANCE_CRITERIA_SCHEMA_VERSION,
        "kind": "max.acceptance_criteria",
        "idea_id": unit.id,
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": unit.id,
            "status": unit.status,
            "domain": unit.domain,
            "category": unit.category,
            "evaluation_available": evaluation is not None,
            "evidence_density_available": evidence_density is not None,
        },
        "summary": {
            "title": unit.title,
            "one_liner": unit.one_liner,
            "target_user": unit.specific_user or unit.target_users,
            "buyer": unit.buyer,
            "workflow_context": unit.workflow_context,
            "recommendation": evaluation.recommendation if evaluation else None,
            "overall_score": evaluation.overall_score if evaluation else None,
        },
        "functional_criteria": functional,
        "non_functional_criteria": non_functional,
        "out_of_scope": _out_of_scope(unit, evaluation),
        "edge_cases": _edge_cases(unit, evaluation, evidence_density),
        "evidence_links": evidence_links,
        "review_checklist": _review_checklist(unit, evaluation, evidence_density, evidence_links),
    }


def render_acceptance_criteria_markdown(criteria: dict[str, Any]) -> str:
    """Render generated acceptance criteria as deterministic Markdown."""
    summary = criteria.get("summary") if isinstance(criteria.get("summary"), dict) else {}
    source = criteria.get("source") if isinstance(criteria.get("source"), dict) else {}
    title = _text(summary.get("title")) or _text(criteria.get("idea_id")) or "Untitled Idea"

    lines = [
        f"# Acceptance Criteria: {title}",
        "",
        f"- Schema version: {_text(criteria.get('schema_version')) or 'none'}",
        f"- Idea ID: {_text(criteria.get('idea_id')) or _text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- Source domain: {_text(source.get('domain')) or 'none'}",
        f"- Source category: {_text(source.get('category')) or 'none'}",
        f"- One-liner: {_text(summary.get('one_liner')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context')) or 'none'}",
        f"- Target user: {_text(summary.get('target_user')) or 'none'}",
        f"- Buyer: {_text(summary.get('buyer')) or 'none'}",
        f"- Recommendation: {_text(summary.get('recommendation')) or 'none'}",
        f"- Overall score: {_text(summary.get('overall_score')) or 'none'}",
        f"- Evaluation available: {_text(source.get('evaluation_available')) or 'none'}",
        (
            "- Evidence density available: "
            f"{_text(source.get('evidence_density_available')) or 'none'}"
        ),
        "",
    ]

    _extend_section(
        lines,
        "Functional Criteria",
        _dict_items(criteria.get("functional_criteria")),
        _render_criterion,
    )
    _extend_section(
        lines,
        "Non-Functional Criteria",
        _dict_items(criteria.get("non_functional_criteria")),
        _render_criterion,
    )
    _extend_section(
        lines,
        "Edge Cases",
        _dict_items(criteria.get("edge_cases")),
        _render_edge_case,
    )
    _extend_section(
        lines,
        "Out of Scope",
        _list_items(criteria.get("out_of_scope")),
        _render_bullet_item,
    )
    _extend_section(
        lines,
        "Evidence Links",
        _dict_items(criteria.get("evidence_links")),
        _render_evidence_link,
    )
    _extend_section(
        lines,
        "Review Checklist",
        _dict_items(criteria.get("review_checklist")),
        _render_review_item,
    )

    return "\n".join(lines).rstrip() + "\n"


def _functional_criteria(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
) -> list[dict[str, Any]]:
    criteria = [
        _criterion(
            "AC-F1",
            "Problem workflow",
            f"The implementation addresses the stated problem: {_compact(unit.problem)}",
            "Run the primary workflow with representative input and verify the output removes or reduces the problem.",
            ["problem", "workflow_context"],
        ),
        _criterion(
            "AC-F2",
            "Solution behavior",
            f"The public interface provides the promised solution: {_compact(unit.solution)}",
            "Exercise the public CLI, API, UI, or library entry point without relying on internals.",
            ["solution", "tech_approach"],
        ),
        _criterion(
            "AC-F3",
            "Target user fit",
            f"The workflow is usable by {_compact(unit.specific_user or unit.target_users)}.",
            "Acceptance notes identify the target user, their input, and the successful completion state.",
            ["specific_user", "target_users"],
        ),
        _criterion(
            "AC-F4",
            "Value delivery",
            f"The MVP demonstrates the value proposition: {_compact(unit.value_proposition)}",
            "A deterministic test or fixture shows the value-producing result.",
            ["value_proposition"],
        ),
    ]

    if unit.validation_plan:
        criteria.append(
            _criterion(
                "AC-F5",
                "Validation plan",
                _compact(unit.validation_plan),
                "The validation plan can be executed locally or has a named blocker.",
                ["validation_plan"],
            )
        )
    if evaluation and evaluation.strengths:
        criteria.append(
            _criterion(
                "AC-F6",
                "Preserve evaluated strengths",
                "The implementation preserves: " + "; ".join(_compact(item) for item in evaluation.strengths if _compact(item)),
                "Review tests and handoff notes against each listed strength.",
                ["evaluation.strengths"],
            )
        )
    return criteria


def _non_functional_criteria(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    evidence_density: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    criteria = [
        _criterion(
            "AC-NF1",
            "Operability",
            "The MVP includes installation, configuration, and first-run instructions.",
            "A fresh checkout can run the primary workflow using documented commands.",
            ["tech_approach", "suggested_stack"],
        ),
        _criterion(
            "AC-NF2",
            "Testability",
            "Core behavior is covered by deterministic automated tests.",
            "Focused tests cover success, failure, and boundary behavior for the primary workflow.",
            ["validation_plan"],
        ),
        _criterion(
            "AC-NF3",
            "Composability",
            _composability_description(unit, evaluation),
            "External integrations and persistence boundaries are isolated behind clear interfaces.",
            ["composability_notes", "evaluation.composability"],
        ),
        _criterion(
            "AC-NF4",
            "Evidence traceability",
            _evidence_description(unit, evidence_density),
            "Handoff includes evidence links or explicitly states that evidence is missing.",
            ["inspiring_insights", "evidence_signals", "evidence_density"],
        ),
    ]
    if unit.domain_risks or (evaluation and evaluation.weaknesses):
        criteria.append(
            _criterion(
                "AC-NF5",
                "Risk visibility",
                "Domain risks and evaluation weaknesses are mapped to tests, notes, or deferred scope.",
                "Each risk or weakness has a visible handling decision before build handoff.",
                ["domain_risks", "evaluation.weaknesses"],
            )
        )
    return criteria


def _out_of_scope(unit: BuildableUnit, evaluation: UtilityEvaluation | None) -> list[str]:
    items = [
        "Broad production launch, paid acquisition, and enterprise rollout are outside the MVP unless explicitly requested.",
        "Unlisted integrations, platforms, and user personas are deferred until the primary workflow is accepted.",
    ]
    if unit.current_workaround:
        items.append(f"Replacing every existing workaround is out of scope; focus first on {_compact(unit.current_workaround)}.")
    if unit.first_10_customers:
        items.append("Serving customers beyond the first pilot cohort is deferred until validation evidence is reviewed.")
    if evaluation:
        items.extend(
            f"Do not expand scope to solve this evaluation weakness without approval: {_compact(weakness)}"
            for weakness in evaluation.weaknesses
            if _compact(weakness)
        )
    return items


def _edge_cases(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    evidence_density: dict[str, Any] | None,
) -> list[dict[str, str]]:
    cases = [
        _edge_case("EC1", "Missing or invalid input", "The public interface returns a clear error without partial side effects."),
        _edge_case("EC2", "No matching workflow data", "The result explains that no actionable output was produced."),
        _edge_case("EC3", "Repeated execution", "Running the same workflow twice produces stable results or documented idempotent behavior."),
    ]
    if not unit.specific_user:
        cases.append(_edge_case("EC4", "Ambiguous persona", "The implementation defaults to the documented target_users value."))
    if evidence_density and evidence_density.get("missing_evidence_warnings"):
        cases.append(_edge_case("EC5", "Missing evidence references", "Acceptance output keeps missing evidence warnings visible."))
    if evaluation and evaluation.weaknesses:
        cases.append(_edge_case("EC6", "Known weakness path", "The highest-priority evaluation weakness is either tested or marked as deferred."))
    return cases


def _evidence_links(unit: BuildableUnit) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for insight_id in unit.inspiring_insights:
        if _compact(insight_id):
            links.append({"type": "insight", "id": insight_id, "uri": f"insights://{insight_id}"})
    for signal_id in unit.evidence_signals:
        if _compact(signal_id):
            links.append({"type": "signal", "id": signal_id, "uri": f"signals://{signal_id}"})
    for idea_id in unit.source_idea_ids:
        if _compact(idea_id):
            links.append({"type": "source_idea", "id": idea_id, "uri": f"ideas://{idea_id}"})
    return links


def _review_checklist(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    evidence_density: dict[str, Any] | None,
    evidence_links: list[dict[str, str]],
) -> list[dict[str, Any]]:
    return [
        _review_item("RC1", "Functional criteria have tests or manual verification notes.", True),
        _review_item("RC2", "Out-of-scope items are copied into the implementation handoff.", True),
        _review_item("RC3", "Edge cases are represented in tests, fixtures, or explicit release notes.", True),
        _review_item("RC4", "Evidence links are present or the lack of evidence is called out.", bool(evidence_links)),
        _review_item("RC5", "Evaluation weaknesses have handling decisions.", bool(evaluation and evaluation.weaknesses)),
        _review_item("RC6", "Evidence density warnings have been reviewed.", bool(evidence_density and evidence_density.get("missing_evidence_warnings"))),
    ]


def _criterion(
    criterion_id: str,
    title: str,
    statement: str,
    verification: str,
    trace_fields: list[str],
) -> dict[str, Any]:
    return {
        "id": criterion_id,
        "title": title,
        "statement": _compact(statement),
        "verification": verification,
        "trace_fields": trace_fields,
    }


def _edge_case(edge_case_id: str, condition: str, expected_behavior: str) -> dict[str, str]:
    return {
        "id": edge_case_id,
        "condition": condition,
        "expected_behavior": expected_behavior,
    }


def _review_item(item_id: str, item: str, evidence_required: bool) -> dict[str, Any]:
    return {
        "id": item_id,
        "item": item,
        "status": "pending",
        "evidence_required": evidence_required,
    }


def _render_criterion(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id')) or 'AC'}: {_text(item.get('title')) or 'Untitled criterion'}",
        f"- Statement: {_text(item.get('statement')) or 'not specified'}",
        f"- Verification: {_text(item.get('verification')) or 'not specified'}",
        f"- Trace fields: {_join_code(item.get('trace_fields'))}",
    ]


def _render_edge_case(item: dict[str, Any]) -> list[str]:
    condition = _text(item.get("condition")) or "Unspecified condition"
    return [
        f"### {_text(item.get('id')) or 'EC'}: {condition}",
        f"- Expected behavior: {_text(item.get('expected_behavior')) or 'not specified'}",
    ]


def _render_bullet_item(item: Any) -> list[str]:
    return [f"- {_text(item) or 'not specified'}"]


def _render_evidence_link(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id')) or 'evidence'}",
        f"- Type: {_text(item.get('type')) or 'none'}",
        f"- URI: {_text(item.get('uri')) or 'none'}",
    ]


def _render_review_item(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id')) or 'RC'}",
        f"- Item: {_text(item.get('item')) or 'not specified'}",
        f"- Status: {_text(item.get('status')) or 'none'}",
        f"- Evidence required: {_text(item.get('evidence_required')) or 'none'}",
    ]


def _extend_section(
    lines: list[str],
    title: str,
    items: list[Any],
    renderer,
) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]


def _list_items(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value


def _join_code(value: Any) -> str:
    items = [_text(item) for item in value or [] if _text(item)]
    if not items:
        return "none"
    return ", ".join(f"`{item}`" for item in items)


def _composability_description(unit: BuildableUnit, evaluation: UtilityEvaluation | None) -> str:
    if unit.composability_notes:
        return unit.composability_notes
    if evaluation:
        score = evaluation.composability
        return f"Composability scored {score.value:.1f}/10: {_compact(score.reasoning)}"
    return "The implementation exposes a narrow, documented boundary for reuse by agents or downstream tools."


def _evidence_description(unit: BuildableUnit, evidence_density: dict[str, Any] | None) -> str:
    link_count = len(unit.inspiring_insights) + len(unit.evidence_signals) + len(unit.source_idea_ids)
    if evidence_density:
        return (
            f"Acceptance criteria trace to {link_count} idea evidence link(s); "
            f"evidence density score is {float(evidence_density.get('density_score') or 0.0):.1f}/100."
        )
    return f"Acceptance criteria trace to {link_count} idea evidence link(s)."


def _compact(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text or "not specified"


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
