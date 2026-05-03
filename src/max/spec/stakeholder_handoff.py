"""Generate deterministic stakeholder handoff artifacts for TactSpec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


STAKEHOLDER_HANDOFF_SCHEMA_VERSION = "max-stakeholder-handoff/v1"
STAKEHOLDER_HANDOFF_CSV_COLUMNS = (
    "schema_version",
    "kind",
    "idea_id",
    "title",
    "section",
    "row_type",
    "item_id",
    "label",
    "role",
    "owner",
    "timing",
    "decision_criteria",
    "evidence_ids",
    "source_references",
    "recommendation",
    "overall_score",
    "source_status",
    "evaluation_available",
    "tact_spec_schema_version",
    "details",
)


def generate_stakeholder_handoff(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    tact_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn a buildable idea into a stable stakeholder handoff artifact."""
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    evaluation_payload = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}

    summary = _summary(unit, evaluation, project, execution, solution)
    evidence_references = _evidence_references(unit, evidence)
    unresolved_risks = _unresolved_risks(unit, evaluation, execution, evaluation_payload)

    return {
        "schema_version": STAKEHOLDER_HANDOFF_SCHEMA_VERSION,
        "kind": "max.stakeholder_handoff",
        "idea_id": unit.id,
        "source": {
            "system": source.get("system") or "max",
            "type": source.get("type") or "idea",
            "idea_id": source.get("idea_id") or unit.id,
            "status": source.get("status") or unit.status,
            "domain": source.get("domain") or unit.domain,
            "category": source.get("category") or unit.category,
            "evaluation_available": evaluation is not None,
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
        },
        "summary": summary,
        "owner_roles": _owner_roles(summary, solution, unresolved_risks),
        "decision_checkpoints": _decision_checkpoints(summary, evaluation, unresolved_risks),
        "evidence_references": evidence_references,
        "launch_readiness_questions": _launch_readiness_questions(summary, unresolved_risks),
        "unresolved_risks": unresolved_risks,
    }


def render_stakeholder_handoff_markdown(handoff: dict[str, Any]) -> str:
    """Render a generated stakeholder handoff as deterministic Markdown."""
    summary = handoff.get("summary", {})
    source = handoff.get("source", {})
    title = _text(summary.get("title")) or _text(handoff.get("idea_id")) or "Idea"

    lines = [
        f"# {title} Stakeholder Handoff",
        "",
        f"- Schema version: {_text(handoff.get('schema_version'))}",
        f"- Idea ID: {_text(handoff.get('idea_id'))}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Recommendation: {_text(summary.get('recommendation')) or 'none'}",
        f"- Overall score: {_text(summary.get('overall_score')) or 'none'}",
        "",
    ]

    _extend_section(lines, "Owner Roles", handoff.get("owner_roles") or [], _render_owner)
    _extend_section(
        lines,
        "Decision Checkpoints",
        handoff.get("decision_checkpoints") or [],
        _render_checkpoint,
    )
    _extend_section(
        lines,
        "Evidence References",
        handoff.get("evidence_references") or [],
        _render_evidence,
    )
    _extend_section(
        lines,
        "Launch-Readiness Questions",
        handoff.get("launch_readiness_questions") or [],
        _render_question,
    )
    _extend_section(
        lines, "Open Risks", handoff.get("unresolved_risks") or [], _render_risk
    )

    return "\n".join(lines).rstrip() + "\n"


def render_stakeholder_handoff_csv(handoff: dict[str, Any]) -> str:
    """Render a generated stakeholder handoff as deterministic CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=STAKEHOLDER_HANDOFF_CSV_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _csv_rows(handoff or {}):
        writer.writerow(row)
    return output.getvalue()


def _summary(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    project: dict[str, Any],
    execution: dict[str, Any],
    solution: dict[str, Any],
) -> dict[str, Any]:
    return {
        "title": _compact(project.get("title")) or unit.title,
        "one_liner": _compact(project.get("summary")) or unit.one_liner,
        "target_user": _compact(
            project.get("specific_user") or unit.specific_user or project.get("target_users")
        )
        or unit.target_users
        or "primary user",
        "buyer": _compact(project.get("buyer") or unit.buyer) or "launch sponsor",
        "workflow_context": _compact(project.get("workflow_context") or unit.workflow_context)
        or f"{unit.title} workflow",
        "primary_scope": _first_string(execution.get("mvp_scope"))
        or unit.solution
        or f"first usable {unit.title} workflow",
        "technical_approach": _compact(
            solution.get("technical_approach") or unit.tech_approach or solution.get("approach")
        )
        or "technical approach is not specified",
        "validation_plan": _compact(execution.get("validation_plan") or unit.validation_plan)
        or "validation plan needs stakeholder confirmation",
        "recommendation": evaluation.recommendation if evaluation else None,
        "overall_score": evaluation.overall_score if evaluation else None,
    }


def _owner_roles(
    summary: dict[str, Any],
    solution: dict[str, Any],
    unresolved_risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    roles = [
        _owner(
            "OR1",
            "product_owner",
            summary["buyer"],
            "Own scope, acceptance decisions, and release priority.",
            ["summary.primary_scope", "decision_checkpoints"],
        ),
        _owner(
            "OR2",
            "technical_owner",
            "engineering lead",
            "Own architecture, implementation sequencing, and technical tradeoffs.",
            ["summary.technical_approach", "solution.suggested_stack"],
        ),
        _owner(
            "OR3",
            "validation_owner",
            summary["target_user"],
            "Own pilot feedback, evidence updates, and validation signoff.",
            ["summary.validation_plan", "evidence_references"],
        ),
        _owner(
            "OR4",
            "launch_owner",
            "release coordinator",
            "Own go/no-go coordination, launch comms, and rollback readiness.",
            ["launch_readiness_questions", "unresolved_risks"],
        ),
    ]
    if solution.get("suggested_stack"):
        roles.append(
            _owner(
                "OR5",
                "platform_owner",
                "platform or infrastructure owner",
                "Confirm runtime, integration, and operational constraints before build starts.",
                ["solution.suggested_stack", "summary.technical_approach"],
            )
        )
    if unresolved_risks:
        roles.append(
            _owner(
                "OR6",
                "risk_owner",
                "named stakeholder for open risks",
                "Track unresolved risks until each is accepted, mitigated, or closed.",
                ["unresolved_risks"],
            )
        )
    return roles


def _decision_checkpoints(
    summary: dict[str, Any],
    evaluation: UtilityEvaluation | None,
    unresolved_risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    checkpoints = [
        _checkpoint(
            "DC1",
            "Scope confirmation",
            "before implementation",
            "product_owner",
            f"MVP scope is limited to {summary['primary_scope']}.",
            ["summary.primary_scope"],
        ),
        _checkpoint(
            "DC2",
            "Technical handoff",
            "before first merge",
            "technical_owner",
            f"Implementation approach is executable: {summary['technical_approach']}.",
            ["summary.technical_approach"],
        ),
        _checkpoint(
            "DC3",
            "Validation review",
            "before launch approval",
            "validation_owner",
            f"Validation evidence satisfies: {summary['validation_plan']}.",
            ["summary.validation_plan", "evidence_references"],
        ),
        _checkpoint(
            "DC4",
            "Go/no-go",
            "launch gate",
            "launch_owner",
            "Owners agree that open risks are accepted or have mitigations.",
            ["unresolved_risks", "launch_readiness_questions"],
        ),
    ]
    if evaluation is None:
        checkpoints.insert(
            0,
            _checkpoint(
                "DC0",
                "Utility evaluation",
                "before build commitment",
                "evaluation_owner",
                "Utility evaluation is missing and must be reviewed or explicitly waived.",
                ["source.evaluation_available"],
            ),
        )
    elif evaluation.recommendation and evaluation.recommendation != "yes":
        checkpoints.append(
            _checkpoint(
                "DC5",
                "Recommendation override",
                "before build commitment",
                "product_owner",
                f"Evaluation recommendation is {evaluation.recommendation}; document the override decision.",
                ["summary.recommendation", "summary.overall_score"],
            )
        )
    if unresolved_risks:
        checkpoints.append(
            _checkpoint(
                "DC6",
                "Risk disposition",
                "before external exposure",
                "risk_owner",
                "Every open risk has an owner, mitigation, and accept-or-block decision.",
                ["unresolved_risks"],
            )
        )
    return checkpoints


def _evidence_references(unit: BuildableUnit, evidence: dict[str, Any]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for insight_id in _list_strings(evidence.get("insight_ids")) or unit.inspiring_insights:
        references.append(
            _evidence(
                f"EV{len(references) + 1}",
                "insight",
                insight_id,
                "Problem, timing, or opportunity evidence used to create the idea.",
            )
        )
    for signal_id in _list_strings(evidence.get("signal_ids")) or unit.evidence_signals:
        references.append(
            _evidence(
                f"EV{len(references) + 1}",
                "signal",
                signal_id,
                "Source signal supporting the idea or validation path.",
            )
        )
    for source_id in _list_strings(evidence.get("source_idea_ids")) or unit.source_idea_ids:
        references.append(
            _evidence(
                f"EV{len(references) + 1}",
                "source_idea",
                source_id,
                "Related idea that contributed context or scope.",
            )
        )
    if not references and _compact(unit.evidence_rationale):
        references.append(
            _evidence(
                "EV1",
                "rationale",
                "evidence_rationale",
                unit.evidence_rationale,
            )
        )
    return references


def _launch_readiness_questions(
    summary: dict[str, Any],
    unresolved_risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    questions = [
        _question(
            "LRQ1",
            "Can the target user complete the MVP workflow without implementation-team help?",
            "validation_owner",
            ["summary.target_user", "summary.workflow_context"],
        ),
        _question(
            "LRQ2",
            "Is the buyer or sponsor ready to judge success from the validation plan?",
            "product_owner",
            ["summary.buyer", "summary.validation_plan"],
        ),
        _question(
            "LRQ3",
            "Are install, configuration, and rollback paths documented for the first release?",
            "technical_owner",
            ["summary.technical_approach"],
        ),
        _question(
            "LRQ4",
            "Is ownership clear for support, telemetry review, and launch decisions?",
            "launch_owner",
            ["owner_roles", "decision_checkpoints"],
        ),
    ]
    if unresolved_risks:
        questions.append(
            _question(
                "LRQ5",
                "Have all open risks been accepted, mitigated, or turned into launch blockers?",
                "risk_owner",
                ["unresolved_risks"],
            )
        )
    return questions


def _unresolved_risks(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    execution: dict[str, Any],
    evaluation_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for risk in _list_strings(execution.get("risks")) or unit.domain_risks:
        risks.append(
            _risk(
                f"UR{len(risks) + 1}",
                "domain_risk",
                risk,
                "high",
                "product_owner",
                ["execution.risks", "unit.domain_risks"],
            )
        )
    if evaluation is None:
        risks.append(
            _risk(
                f"UR{len(risks) + 1}",
                "missing_evaluation",
                "Utility evaluation is missing, so score-based build risk has not been reviewed.",
                "high",
                "evaluation_owner",
                ["source.evaluation_available"],
            )
        )
    else:
        for weakness in evaluation.weaknesses:
            if _compact(weakness):
                risks.append(
                    _risk(
                        f"UR{len(risks) + 1}",
                        "evaluation_weakness",
                        weakness,
                        "medium",
                        "product_owner",
                        ["evaluation.weaknesses"],
                    )
                )
        for name, dimension in sorted((evaluation_payload.get("dimensions") or {}).items()):
            if isinstance(dimension, dict) and (dimension.get("confidence") or 0) < 0.5:
                risks.append(
                    _risk(
                        f"UR{len(risks) + 1}",
                        "low_confidence_dimension",
                        f"{name} confidence is {dimension.get('confidence')}.",
                        "medium",
                        "evaluation_owner",
                        [f"evaluation.dimensions.{name}"],
                    )
                )
    if not _compact(unit.workflow_context):
        risks.append(
            _risk(
                f"UR{len(risks) + 1}",
                "missing_workflow_context",
                "Workflow context is missing and may cause ambiguous handoff decisions.",
                "high",
                "product_owner",
                ["project.workflow_context"],
            )
        )
    return _dedupe_risks(risks)


def _owner(
    item_id: str,
    role: str,
    suggested_owner: str,
    responsibility: str,
    references: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "role": role,
        "suggested_owner": suggested_owner,
        "responsibility": responsibility,
        "references": references,
    }


def _checkpoint(
    item_id: str,
    name: str,
    timing: str,
    owner_role: str,
    decision_needed: str,
    references: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "timing": timing,
        "owner_role": owner_role,
        "decision_needed": decision_needed,
        "references": references,
    }


def _evidence(item_id: str, reference_type: str, reference_id: str, description: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": reference_type,
        "reference_id": reference_id,
        "description": description,
    }


def _question(
    item_id: str, question: str, owner_role: str, references: list[str]
) -> dict[str, Any]:
    return {
        "id": item_id,
        "question": question,
        "owner_role": owner_role,
        "references": references,
    }


def _risk(
    item_id: str,
    category: str,
    description: str,
    severity: str,
    owner_role: str,
    references: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "category": category,
        "description": description,
        "severity": severity,
        "owner_role": owner_role,
        "references": references,
        "status": "open",
    }


def _extend_section(
    lines: list[str],
    title: str,
    items: list[dict[str, Any]],
    renderer,
) -> None:
    lines.extend([f"## {title}", ""])
    if items:
        for item in items:
            lines.extend(renderer(item))
    else:
        lines.extend(["None.", ""])


def _render_owner(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('role'))}",
        "",
        f"- Suggested owner: {_text(item.get('suggested_owner'))}",
        f"- Responsibility: {_text(item.get('responsibility'))}",
        f"- References: {_join(item.get('references'))}",
        "",
    ]


def _render_checkpoint(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        "",
        f"- Timing: {_text(item.get('timing'))}",
        f"- Owner role: {_text(item.get('owner_role'))}",
        f"- Decision needed: {_text(item.get('decision_needed'))}",
        f"- References: {_join(item.get('references'))}",
        "",
    ]


def _render_evidence(item: dict[str, Any]) -> list[str]:
    return [
        f"- {_text(item.get('id'))} [{_text(item.get('type'))}]: "
        f"{_text(item.get('reference_id'))} - {_text(item.get('description'))}"
    ]


def _render_question(item: dict[str, Any]) -> list[str]:
    return [
        f"- {_text(item.get('id'))} [{_text(item.get('owner_role'))}]: "
        f"{_text(item.get('question'))}"
    ]


def _render_risk(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('category'))}",
        "",
        f"- Severity: {_text(item.get('severity'))}",
        f"- Owner role: {_text(item.get('owner_role'))}",
        f"- Status: {_text(item.get('status'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- References: {_join(item.get('references'))}",
        "",
    ]


def _dedupe_risks(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for risk in risks:
        key = (_text(risk.get("category")), _text(risk.get("description")).lower())
        if key in seen:
            continue
        seen.add(key)
        risk = dict(risk)
        risk["id"] = f"UR{len(deduped) + 1}"
        deduped.append(risk)
    return deduped


def _csv_rows(handoff: dict[str, Any]) -> list[dict[str, str]]:
    summary = handoff.get("summary") if isinstance(handoff.get("summary"), dict) else {}
    rows = [
        _csv_row(
            handoff,
            section="summary",
            row_type="summary",
            item_id="SUMMARY",
            label=summary.get("title"),
            role=summary.get("target_user"),
            owner=summary.get("buyer"),
            timing=summary.get("workflow_context"),
            decision_criteria=summary.get("validation_plan"),
            source_references=[
                "summary.target_user",
                "summary.buyer",
                "summary.validation_plan",
            ],
            details={
                "one_liner": summary.get("one_liner"),
                "primary_scope": summary.get("primary_scope"),
                "technical_approach": summary.get("technical_approach"),
            },
        )
    ]
    for role in handoff.get("owner_roles") or []:
        rows.append(
            _csv_row(
                handoff,
                section="owner_roles",
                row_type="owner_role",
                item_id=role.get("id"),
                label=role.get("role"),
                role=role.get("role"),
                owner=role.get("suggested_owner"),
                decision_criteria=role.get("responsibility"),
                source_references=role.get("references"),
            )
        )
    for checkpoint in handoff.get("decision_checkpoints") or []:
        rows.append(
            _csv_row(
                handoff,
                section="decision_checkpoints",
                row_type="decision_checkpoint",
                item_id=checkpoint.get("id"),
                label=checkpoint.get("name"),
                role=checkpoint.get("owner_role"),
                owner=checkpoint.get("owner_role"),
                timing=checkpoint.get("timing"),
                decision_criteria=checkpoint.get("decision_needed"),
                source_references=checkpoint.get("references"),
            )
        )
    for evidence in handoff.get("evidence_references") or []:
        rows.append(
            _csv_row(
                handoff,
                section="evidence_references",
                row_type="evidence_reference",
                item_id=evidence.get("id"),
                label=evidence.get("reference_id"),
                evidence_ids=[evidence.get("id")],
                source_references=[evidence.get("reference_id")],
                decision_criteria=evidence.get("description"),
                details={"type": evidence.get("type")},
            )
        )
    for question in handoff.get("launch_readiness_questions") or []:
        rows.append(
            _csv_row(
                handoff,
                section="launch_readiness_questions",
                row_type="launch_readiness_question",
                item_id=question.get("id"),
                label=question.get("question"),
                role=question.get("owner_role"),
                owner=question.get("owner_role"),
                decision_criteria=question.get("question"),
                source_references=question.get("references"),
            )
        )
    for risk in handoff.get("unresolved_risks") or []:
        rows.append(
            _csv_row(
                handoff,
                section="unresolved_risks",
                row_type="risk",
                item_id=risk.get("id"),
                label=risk.get("category"),
                role=risk.get("owner_role"),
                owner=risk.get("owner_role"),
                decision_criteria=risk.get("description"),
                source_references=risk.get("references"),
                details={
                    "severity": risk.get("severity"),
                    "status": risk.get("status"),
                },
            )
        )
    rows.extend(_generic_csv_rows(handoff))
    return rows


def _generic_csv_rows(handoff: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    rows.extend(
        _generic_section_rows(
            handoff,
            "stakeholder_groups",
            "stakeholder_group",
            ("stakeholder_groups", "stakeholders"),
            label_keys=("stakeholder", "group", "name", "role", "audience"),
            role_keys=("role", "stakeholder_role"),
            owner_keys=("owner", "suggested_owner", "assigned_to"),
            timing_keys=("timing", "cadence"),
            criteria_keys=("responsibility", "description", "summary"),
        )
    )
    rows.extend(
        _generic_section_rows(
            handoff,
            "responsibilities",
            "responsibility",
            ("responsibilities",),
            label_keys=("responsibility", "name", "title", "description"),
            role_keys=("stakeholder", "role", "owner_role"),
            owner_keys=("owner", "suggested_owner", "assigned_to"),
            timing_keys=("timing", "cadence"),
            criteria_keys=("responsibility", "description", "acceptance"),
        )
    )
    rows.extend(
        _generic_section_rows(
            handoff,
            "artifacts",
            "artifact",
            ("artifacts",),
            label_keys=("artifact", "title", "name", "key"),
            role_keys=("role", "owner_role"),
            owner_keys=("owner", "suggested_owner", "assigned_to"),
            timing_keys=("timing", "cadence"),
            criteria_keys=("description", "purpose", "status"),
        )
    )
    rows.extend(
        _generic_section_rows(
            handoff,
            "decisions",
            "decision",
            ("decisions",),
            label_keys=("decision", "name", "title"),
            role_keys=("role", "owner_role", "decider"),
            owner_keys=("owner", "decider", "assigned_to"),
            timing_keys=("timing", "due", "deadline"),
            criteria_keys=("decision", "criteria", "decision_criteria", "description"),
        )
    )
    rows.extend(
        _generic_section_rows(
            handoff,
            "open_questions",
            "open_question",
            ("open_questions", "questions"),
            label_keys=("question", "name", "title"),
            role_keys=("role", "owner_role"),
            owner_keys=("owner", "suggested_owner", "assigned_to"),
            timing_keys=("timing", "due", "deadline"),
            criteria_keys=("question", "description"),
        )
    )
    rows.extend(
        _generic_section_rows(
            handoff,
            "success_criteria",
            "success_criterion",
            ("success_criteria", "success_metrics"),
            label_keys=("criterion", "metric", "name", "title", "description"),
            role_keys=("role", "owner_role"),
            owner_keys=("owner", "suggested_owner", "assigned_to"),
            timing_keys=("timing", "cadence"),
            criteria_keys=("criterion", "target", "description", "measurement"),
        )
    )
    rows.extend(
        _generic_section_rows(
            handoff,
            "follow_up_actions",
            "follow_up_action",
            ("follow_up_actions", "followups", "actions"),
            label_keys=("action", "follow_up_action", "name", "title", "description"),
            role_keys=("role", "owner_role"),
            owner_keys=("owner", "suggested_owner", "assigned_to"),
            timing_keys=("timing", "due", "deadline"),
            criteria_keys=("action", "follow_up_action", "description"),
        )
    )
    return rows


def _generic_section_rows(
    handoff: dict[str, Any],
    section: str,
    row_type: str,
    keys: tuple[str, ...],
    *,
    label_keys: tuple[str, ...],
    role_keys: tuple[str, ...],
    owner_keys: tuple[str, ...],
    timing_keys: tuple[str, ...],
    criteria_keys: tuple[str, ...],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key in keys:
        for index, item in enumerate(_dict_items(handoff.get(key)), start=1):
            item_id = _first_value(item, ("id", "item_id", "key")) or f"{row_type.upper()}{index}"
            evidence_ids = _first_value(
                item, ("evidence_ids", "evidence_reference_ids", "evidence_references")
            )
            source_references = _first_value(
                item, ("source_references", "references", "reference_ids")
            )
            rows.append(
                _csv_row(
                    handoff,
                    section=section,
                    row_type=row_type,
                    item_id=item_id,
                    label=_first_value(item, label_keys),
                    role=_first_value(item, role_keys),
                    owner=_first_value(item, owner_keys),
                    timing=_first_value(item, timing_keys),
                    decision_criteria=_first_value(item, criteria_keys),
                    evidence_ids=evidence_ids,
                    source_references=source_references,
                    details=_remaining_details(
                        item,
                        {
                            "id",
                            "item_id",
                            "key",
                            *label_keys,
                            *role_keys,
                            *owner_keys,
                            *timing_keys,
                            *criteria_keys,
                            "evidence_ids",
                            "evidence_reference_ids",
                            "evidence_references",
                            "source_references",
                            "references",
                            "reference_ids",
                        },
                    ),
                )
            )
        if rows and any(row["section"] == section for row in rows):
            break
    return rows


def _csv_row(
    handoff: dict[str, Any],
    *,
    section: str,
    row_type: str,
    item_id: Any = "",
    label: Any = "",
    role: Any = "",
    owner: Any = "",
    timing: Any = "",
    decision_criteria: Any = "",
    evidence_ids: Any = None,
    source_references: Any = None,
    details: dict[str, Any] | None = None,
) -> dict[str, str]:
    summary = handoff.get("summary") if isinstance(handoff.get("summary"), dict) else {}
    source = handoff.get("source") if isinstance(handoff.get("source"), dict) else {}
    return {
        "schema_version": _csv_text(handoff.get("schema_version")),
        "kind": _csv_text(handoff.get("kind")),
        "idea_id": _csv_text(handoff.get("idea_id")),
        "title": _csv_text(summary.get("title")),
        "section": section,
        "row_type": row_type,
        "item_id": _csv_text(item_id),
        "label": _csv_text(label),
        "role": _csv_text(role),
        "owner": _csv_text(owner),
        "timing": _csv_text(timing),
        "decision_criteria": _csv_text(decision_criteria),
        "evidence_ids": _csv_join(evidence_ids),
        "source_references": _csv_join(source_references),
        "recommendation": _csv_text(summary.get("recommendation")),
        "overall_score": _csv_text(summary.get("overall_score")),
        "source_status": _csv_text(source.get("status")),
        "evaluation_available": _csv_text(source.get("evaluation_available")),
        "tact_spec_schema_version": _csv_text(source.get("tact_spec_schema_version")),
        "details": _csv_details(details),
    }


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _first_value(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = item.get(key)
        if isinstance(value, list):
            if _csv_join(value):
                return value
        elif _csv_text(value):
            return value
    return ""


def _remaining_details(item: dict[str, Any], used_keys: set[str]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if key not in used_keys and _csv_text(value)
    }


def _first_string(value: Any) -> str:
    for item in _list_strings(value):
        return item
    return ""


def _list_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_compact(item) for item in value if _compact(item)]


def _join(value: Any) -> str:
    items = _list_strings(value)
    return ", ".join(items) if items else "none"


def _compact(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.1f}"
    return _compact(value)


def _csv_join(values: Any) -> str:
    if isinstance(values, list):
        return " | ".join(_csv_text(value) for value in values if _csv_text(value))
    return _csv_text(values)


def _csv_details(details: dict[str, Any] | None) -> str:
    if not details:
        return ""
    return "; ".join(
        f"{key}={_csv_join(value)}"
        for key, value in sorted(details.items())
        if _csv_join(value)
    )
