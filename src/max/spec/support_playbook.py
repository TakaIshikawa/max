"""Generate deterministic customer-support playbooks for buildable specs."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


SUPPORT_PLAYBOOK_SCHEMA_VERSION = "max-support-playbook/v1"
CSV_COLUMNS: tuple[str, ...] = (
    "idea_id",
    "section",
    "item_id",
    "title_or_question",
    "trigger",
    "action",
    "owner_or_path",
    "expected_outcome",
    "related_evidence",
    "evaluation_available",
    "tact_spec_available",
    "tact_spec_schema_version",
)

_DIMENSION_NAMES = (
    "pain_severity",
    "addressable_scale",
    "build_effort",
    "composability",
    "competitive_density",
    "timing_fit",
    "compounding_value",
)


def generate_support_playbook(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    tact_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn a buildable idea into deterministic support handoff guidance."""
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    spec_project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    spec_execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    spec_evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}

    idea = _idea_summary(unit, evaluation, spec_project, spec_execution)
    risks = _risk_notes(unit, evaluation, spec_execution, spec_evidence)
    scenarios = _support_scenarios(idea, risks)

    return {
        "schema_version": SUPPORT_PLAYBOOK_SCHEMA_VERSION,
        "kind": "max.support_playbook",
        "idea_id": unit.id,
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": unit.id,
            "status": unit.status,
            "domain": unit.domain,
            "category": unit.category,
            "evaluation_available": evaluation is not None,
            "tact_spec_available": bool(spec),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
        },
        "idea_summary": idea,
        "support_scenarios": scenarios,
        "triage_questions": _triage_questions(idea, risks),
        "escalation_paths": _escalation_paths(idea, risks),
        "known_limitations": _known_limitations(unit, evaluation, spec_execution),
        "troubleshooting_checklist": _troubleshooting_checklist(idea, risks),
        "evidence_risk_notes": risks,
    }


def render_support_playbook_markdown(playbook: dict[str, Any]) -> str:
    """Render a generated support playbook as a deterministic Markdown document."""
    summary = playbook.get("idea_summary", {})
    source = playbook.get("source", {})
    title = _text(summary.get("title")) or _text(playbook.get("idea_id")) or "Idea"

    lines = [
        f"# {title} Support Playbook",
        "",
        f"- Schema version: {_text(playbook.get('schema_version'))}",
        f"- Idea ID: {_text(playbook.get('idea_id'))}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- Category: {_text(source.get('category')) or 'none'}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Primary scope: {_text(summary.get('primary_scope'))}",
        f"- Recommendation: {_text(summary.get('recommendation')) or 'none'}",
        f"- Overall score: {_text(summary.get('overall_score')) or 'none'}",
        "",
    ]

    _extend_section(
        lines, "Likely Support Scenarios", playbook.get("support_scenarios") or [], _render_scenario
    )
    _extend_section(
        lines, "Triage Questions", playbook.get("triage_questions") or [], _render_question
    )
    _extend_section(
        lines, "Escalation Paths", playbook.get("escalation_paths") or [], _render_escalation
    )
    _extend_section(
        lines, "Known Limitations", playbook.get("known_limitations") or [], _render_limitation
    )
    _extend_section(
        lines,
        "Troubleshooting Checklist",
        playbook.get("troubleshooting_checklist") or [],
        _render_checklist_item,
    )
    _extend_section(
        lines,
        "Evidence-Linked Risk Notes",
        playbook.get("evidence_risk_notes") or [],
        _render_risk_note,
    )

    lines.extend(
        [
            "## Source Flags",
            "",
            f"- Evaluation available: {_text(source.get('evaluation_available'))}",
            f"- Tact spec available: {_text(source.get('tact_spec_available'))}",
            f"- Tact spec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_support_playbook_csv(playbook: dict[str, Any]) -> str:
    """Render a generated support playbook as deterministic CSV."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(playbook):
        writer.writerow(row)
    return output.getvalue()


def _idea_summary(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    project: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    target_user = _compact(
        project.get("specific_user")
        or unit.specific_user
        or project.get("target_users")
        or unit.target_users
    )
    buyer = _compact(project.get("buyer") or unit.buyer) or "support sponsor"
    workflow = (
        _compact(project.get("workflow_context") or unit.workflow_context)
        or f"{unit.title} workflow"
    )
    scope = (
        _first_string(execution.get("mvp_scope"))
        or unit.solution
        or f"first usable {unit.title} workflow"
    )

    return {
        "title": _compact(project.get("title")) or unit.title,
        "one_liner": _compact(project.get("summary")) or unit.one_liner,
        "target_user": target_user or "primary user",
        "buyer": buyer,
        "workflow_context": workflow,
        "primary_scope": scope,
        "current_workaround": unit.current_workaround or "current manual process",
        "validation_plan": _compact(execution.get("validation_plan"))
        or unit.validation_plan
        or f"Validate {workflow}.",
        "recommendation": evaluation.recommendation if evaluation else None,
        "overall_score": evaluation.overall_score if evaluation else None,
        "support_goal": f"Help {_compact(target_user) or 'primary users'} complete {workflow}.",
    }


def _support_scenarios(
    idea: dict[str, Any],
    risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    primary_risk = (
        risks[0]["note"] if risks else "Support receives a request not covered by launch notes."
    )
    return [
        _scenario(
            "SC1",
            "User cannot complete primary workflow",
            f"{idea['target_user']} reports that {idea['workflow_context']} is blocked.",
            "Missing setup, changed input, or release defect in the primary workflow.",
            "Confirm the exact step, collect the failing input, and run the troubleshooting checklist.",
            "Restore the user path or escalate with reproduction evidence.",
            ["idea.workflow_context", "idea.validation_plan"],
        ),
        _scenario(
            "SC2",
            "Expected value is unclear",
            f"{idea['target_user']} cannot connect the output to {idea['primary_scope']}.",
            "The first-release scope or customer expectation was not communicated clearly.",
            "Restate the supported scope, compare against the validation plan, and capture the gap.",
            "Clarify expected behavior or file a product follow-up for unsupported demand.",
            ["idea.primary_scope", "idea.one_liner"],
        ),
        _scenario(
            "SC3",
            "Known risk appears in support intake",
            primary_risk,
            "A pre-launch risk has materialized during customer use.",
            "Link the ticket to the risk note, identify severity, and start the matching escalation path.",
            "Owner accepts, mitigates, or waives the risk with customer-facing guidance.",
            ["evidence_risk_notes"],
        ),
        _scenario(
            "SC4",
            "Evidence or evaluation context is missing",
            "Support cannot explain why the feature was approved or how it was validated.",
            "Evaluation, preview, or evidence links were absent or incomplete at handoff.",
            "Use the fallback summary and ask the product owner for approval context.",
            "Support notes are updated with the missing evidence or an explicit waiver.",
            ["source.evaluation_available", "source.tact_spec_available"],
        ),
    ]


def _triage_questions(
    idea: dict[str, Any],
    risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    questions = [
        _question(
            "TQ1",
            "Who is affected?",
            f"Is the requester the expected {idea['target_user']} or another role?",
            "support_owner",
            ["idea.target_user"],
        ),
        _question(
            "TQ2",
            "Where did it fail?",
            f"Which step of {idea['workflow_context']} failed, and what input was used?",
            "support_owner",
            ["idea.workflow_context"],
        ),
        _question(
            "TQ3",
            "What changed?",
            "Did this begin after a release, configuration change, integration outage, or new customer data?",
            "technical_owner",
            ["release_notes", "configuration"],
        ),
        _question(
            "TQ4",
            "Can the validation path reproduce it?",
            idea["validation_plan"],
            "qa_owner",
            ["idea.validation_plan"],
        ),
    ]
    if risks:
        questions.append(
            _question(
                "TQ5",
                "Does it match a known risk?",
                f"Compare the ticket against {risks[0]['id']} and any linked evidence.",
                "product_owner",
                ["evidence_risk_notes"],
            )
        )
    return questions


def _escalation_paths(
    idea: dict[str, Any],
    risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    paths = [
        _escalation(
            "ESC1",
            "support_owner",
            "standard",
            "Question can be answered from the playbook and does not block the primary workflow.",
            "Respond in the customer support channel and record the outcome.",
            "same business day",
            ["support_scenarios"],
        ),
        _escalation(
            "ESC2",
            "technical_owner",
            "high",
            f"{idea['workflow_context']} fails for a pilot customer or cannot be reproduced by support.",
            "Open an engineering issue with reproduction steps, logs, and customer impact.",
            "4 business hours",
            ["triage_questions", "troubleshooting_checklist"],
        ),
        _escalation(
            "ESC3",
            "product_owner",
            "high",
            "Customer request falls outside MVP scope or contradicts the approved value proposition.",
            "Decide whether to document the limitation, change scope, or offer a workaround.",
            "1 business day",
            ["idea.primary_scope", "known_limitations"],
        ),
    ]
    if risks:
        paths.append(
            _escalation(
                "ESC4",
                "launch_owner",
                "critical",
                "A high-confidence risk note materializes or customer data integrity may be affected.",
                "Start incident review, pause rollout if needed, and notify the buyer.",
                "1 hour",
                ["evidence_risk_notes"],
            )
        )
    return paths


def _known_limitations(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    execution: dict[str, Any],
) -> list[dict[str, Any]]:
    limitations = [
        _limitation(
            "LIM1",
            "First-release scope",
            _first_string(execution.get("mvp_scope"))
            or unit.solution
            or "MVP scope is not fully specified.",
            "Treat requests outside this scope as product feedback unless they block the documented workflow.",
            ["execution.mvp_scope", "unit.solution"],
        ),
        _limitation(
            "LIM2",
            "Current workaround still matters",
            unit.current_workaround or "No current workaround was provided.",
            "Keep the workaround available until validation proves the new workflow is reliable.",
            ["unit.current_workaround"],
        ),
    ]
    if evaluation is None:
        limitations.append(
            _limitation(
                "LIM3",
                "Evaluation not attached",
                "No utility evaluation is available for support handoff.",
                "Route approval, priority, and customer-fit questions to the product owner.",
                ["evaluation"],
            )
        )
    elif evaluation.weaknesses:
        limitations.append(
            _limitation(
                "LIM3",
                "Evaluation weakness",
                evaluation.weaknesses[0],
                "Mention as a known limitation only after product-owner approval.",
                ["evaluation.weaknesses"],
            )
        )
    return limitations


def _troubleshooting_checklist(
    idea: dict[str, Any],
    risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    checklist = [
        _check(
            "CHK1",
            "Confirm requester and account context.",
            "support_owner",
            "Requester role and customer impact are recorded.",
            ["triage_questions.TQ1"],
        ),
        _check(
            "CHK2",
            f"Reproduce {idea['workflow_context']} with the reported input.",
            "support_owner",
            "Failure is reproduced or marked intermittent with timestamps.",
            ["triage_questions.TQ2"],
        ),
        _check(
            "CHK3",
            "Compare behavior against the validation plan.",
            "qa_owner",
            "Expected behavior, actual behavior, and validation gap are documented.",
            ["idea.validation_plan"],
        ),
        _check(
            "CHK4",
            "Check release, configuration, and integration changes.",
            "technical_owner",
            "Recent changes are ruled in or out.",
            ["triage_questions.TQ3"],
        ),
        _check(
            "CHK5",
            "Send customer-safe status and next step.",
            "support_owner",
            "Customer receives current status, workaround, and follow-up owner.",
            ["support_scenarios"],
        ),
    ]
    if risks:
        checklist.append(
            _check(
                "CHK6",
                "Attach matching evidence-linked risk note.",
                "product_owner",
                "Ticket links to risk note or explicitly states no known risk matched.",
                ["evidence_risk_notes"],
            )
        )
    return checklist


def _risk_notes(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    execution: dict[str, Any],
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    evidence_refs = _evidence_refs(unit, evidence)
    explicit_risks = [*_string_list(execution.get("risks")), *unit.domain_risks]
    for index, risk in enumerate(_dedupe(explicit_risks), start=1):
        notes.append(
            _risk_note(
                f"RN{index}",
                "explicit_risk",
                risk,
                "elevated",
                evidence_refs or ["unit.domain_risks"],
                "Escalate if this appears in a customer ticket or validation run.",
            )
        )

    if evaluation is None:
        notes.append(
            _risk_note(
                f"RN{len(notes) + 1}",
                "missing_evaluation",
                "No utility evaluation is available, so support should not infer priority or customer fit from scores.",
                "elevated",
                evidence_refs,
                "Route prioritization and launch-readiness questions to the product owner.",
            )
        )
    else:
        low_scores = [
            name
            for name in _DIMENSION_NAMES
            if getattr(evaluation, name).value < 6.0 or getattr(evaluation, name).confidence < 0.5
        ]
        if low_scores:
            notes.append(
                _risk_note(
                    f"RN{len(notes) + 1}",
                    "evaluation_signal",
                    f"Evaluation has weak or low-confidence dimensions: {', '.join(low_scores)}.",
                    "elevated",
                    ["evaluation.dimensions"],
                    "Ask the product owner before promising broad applicability.",
                )
            )
        for weakness in evaluation.weaknesses[:2]:
            notes.append(
                _risk_note(
                    f"RN{len(notes) + 1}",
                    "evaluation_weakness",
                    weakness,
                    "standard",
                    ["evaluation.weaknesses"],
                    "Use as context when classifying repeat tickets.",
                )
            )

    if not evidence_refs:
        notes.append(
            _risk_note(
                f"RN{len(notes) + 1}",
                "missing_evidence",
                "No insight or signal identifiers are attached to the idea.",
                "standard",
                [],
                "Ask for evidence before treating anecdotal support volume as validation.",
            )
        )
    return notes


def _scenario(
    scenario_id: str,
    name: str,
    trigger: str,
    likely_cause: str,
    first_response: str,
    resolution_target: str,
    evidence_links: list[str],
) -> dict[str, Any]:
    return {
        "id": scenario_id,
        "name": name,
        "trigger": trigger,
        "likely_cause": likely_cause,
        "triage_questions": ["TQ1", "TQ2", "TQ3"],
        "first_response": first_response,
        "resolution_target": resolution_target,
        "evidence_links": evidence_links,
    }


def _question(
    question_id: str,
    prompt: str,
    detail: str,
    owner: str,
    derived_from: list[str],
) -> dict[str, Any]:
    return {
        "id": question_id,
        "prompt": prompt,
        "detail": detail,
        "owner": owner,
        "derived_from": derived_from,
    }


def _escalation(
    escalation_id: str,
    owner: str,
    severity: str,
    escalate_when: str,
    path: str,
    response_sla: str,
    evidence_links: list[str],
) -> dict[str, Any]:
    return {
        "id": escalation_id,
        "owner": owner,
        "severity": severity,
        "escalate_when": escalate_when,
        "path": path,
        "response_sla": response_sla,
        "evidence_links": evidence_links,
    }


def _limitation(
    limitation_id: str,
    name: str,
    description: str,
    support_guidance: str,
    evidence_links: list[str],
) -> dict[str, Any]:
    return {
        "id": limitation_id,
        "name": name,
        "description": description,
        "support_guidance": support_guidance,
        "evidence_links": evidence_links,
    }


def _check(
    check_id: str,
    task: str,
    owner: str,
    done_when: str,
    evidence_links: list[str],
) -> dict[str, Any]:
    return {
        "id": check_id,
        "task": task,
        "owner": owner,
        "status": "pending",
        "done_when": done_when,
        "evidence_links": evidence_links,
    }


def _risk_note(
    note_id: str,
    source: str,
    note: str,
    severity: str,
    evidence_links: list[str],
    support_action: str,
) -> dict[str, Any]:
    return {
        "id": note_id,
        "source": source,
        "severity": severity,
        "note": note,
        "evidence_links": evidence_links,
        "support_action": support_action,
    }


def _extend_section(
    lines: list[str],
    title: str,
    items: list[dict[str, Any]],
    renderer,
) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _render_scenario(scenario: dict[str, Any]) -> list[str]:
    return [
        f"### {scenario['id']}: {scenario['name']}",
        "",
        f"- Trigger: {scenario['trigger']}",
        f"- Likely cause: {scenario['likely_cause']}",
        f"- Triage questions: {', '.join(scenario.get('triage_questions') or [])}",
        f"- First response: {scenario['first_response']}",
        f"- Resolution target: {scenario['resolution_target']}",
        f"- Evidence links: {_join(scenario.get('evidence_links'))}",
    ]


def _render_question(question: dict[str, Any]) -> list[str]:
    return [
        f"### {question['id']}: {question['prompt']}",
        "",
        f"- Detail: {question['detail']}",
        f"- Owner: {question['owner']}",
        f"- Derived from: {_join(question.get('derived_from'))}",
    ]


def _render_escalation(escalation: dict[str, Any]) -> list[str]:
    return [
        f"### {escalation['id']}: {escalation['owner']} ({escalation['severity']})",
        "",
        f"- Escalate when: {escalation['escalate_when']}",
        f"- Path: {escalation['path']}",
        f"- Response SLA: {escalation['response_sla']}",
        f"- Evidence links: {_join(escalation.get('evidence_links'))}",
    ]


def _render_limitation(limitation: dict[str, Any]) -> list[str]:
    return [
        f"### {limitation['id']}: {limitation['name']}",
        "",
        f"- Description: {limitation['description']}",
        f"- Support guidance: {limitation['support_guidance']}",
        f"- Evidence links: {_join(limitation.get('evidence_links'))}",
    ]


def _render_checklist_item(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item['id']}: {item['task']}",
        "",
        f"- Owner: {item['owner']}",
        f"- Status: {item['status']}",
        f"- Done when: {item['done_when']}",
        f"- Evidence links: {_join(item.get('evidence_links'))}",
    ]


def _render_risk_note(note: dict[str, Any]) -> list[str]:
    return [
        f"### {note['id']}: {note['source']} ({note['severity']})",
        "",
        f"- Note: {note['note']}",
        f"- Evidence links: {_join(note.get('evidence_links'))}",
        f"- Support action: {note['support_action']}",
    ]


def _csv_rows(playbook: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for scenario in _dict_items(playbook.get("support_scenarios")):
        rows.append(
            _csv_row(
                playbook,
                section="support_scenarios",
                item_id=scenario.get("id"),
                title_or_question=scenario.get("name"),
                trigger=scenario.get("trigger"),
                action=scenario.get("first_response"),
                owner_or_path=_join(scenario.get("triage_questions")),
                expected_outcome=scenario.get("resolution_target"),
                related_evidence=scenario.get("evidence_links"),
            )
        )

    for question in _dict_items(playbook.get("triage_questions")):
        rows.append(
            _csv_row(
                playbook,
                section="triage_questions",
                item_id=question.get("id"),
                title_or_question=question.get("prompt"),
                trigger=question.get("detail"),
                action=question.get("detail"),
                owner_or_path=question.get("owner"),
                expected_outcome="Answer captured for support triage.",
                related_evidence=question.get("derived_from"),
            )
        )

    for escalation in _dict_items(playbook.get("escalation_paths")):
        rows.append(
            _csv_row(
                playbook,
                section="escalation_paths",
                item_id=escalation.get("id"),
                title_or_question=escalation.get("severity"),
                trigger=escalation.get("escalate_when"),
                action=escalation.get("path"),
                owner_or_path=escalation.get("owner"),
                expected_outcome=escalation.get("response_sla"),
                related_evidence=escalation.get("evidence_links"),
            )
        )

    for limitation in _dict_items(playbook.get("known_limitations")):
        rows.append(
            _csv_row(
                playbook,
                section="known_limitations",
                item_id=limitation.get("id"),
                title_or_question=limitation.get("name"),
                trigger=limitation.get("description"),
                action=limitation.get("support_guidance"),
                expected_outcome="Limitation documented or routed to product owner.",
                related_evidence=limitation.get("evidence_links"),
            )
        )

    for item in _dict_items(playbook.get("troubleshooting_checklist")):
        rows.append(
            _csv_row(
                playbook,
                section="troubleshooting_checklist",
                item_id=item.get("id"),
                title_or_question=item.get("task"),
                action=item.get("task"),
                owner_or_path=item.get("owner"),
                expected_outcome=item.get("done_when"),
                related_evidence=item.get("evidence_links"),
            )
        )

    for note in _dict_items(playbook.get("evidence_risk_notes")):
        rows.append(
            _csv_row(
                playbook,
                section="evidence_risk_notes",
                item_id=note.get("id"),
                title_or_question=note.get("note"),
                trigger=note.get("severity"),
                action=note.get("support_action"),
                owner_or_path=note.get("source"),
                expected_outcome="Risk note linked to support handling.",
                related_evidence=note.get("evidence_links"),
            )
        )

    source = playbook.get("source") if isinstance(playbook.get("source"), dict) else {}
    if any(
        key in source
        for key in ("evaluation_available", "tact_spec_available", "tact_spec_schema_version")
    ):
        rows.append(
            _csv_row(
                playbook,
                section="source_flags",
                item_id="source",
                title_or_question="Source availability",
                expected_outcome=source.get("tact_spec_kind"),
            )
        )

    return rows


def _csv_row(
    playbook: dict[str, Any],
    *,
    section: str,
    item_id: Any = None,
    title_or_question: Any = None,
    trigger: Any = None,
    action: Any = None,
    owner_or_path: Any = None,
    expected_outcome: Any = None,
    related_evidence: Any = None,
) -> dict[str, str]:
    source = playbook.get("source") if isinstance(playbook.get("source"), dict) else {}
    values = {
        "idea_id": playbook.get("idea_id") or source.get("idea_id"),
        "section": section,
        "item_id": item_id,
        "title_or_question": title_or_question,
        "trigger": trigger,
        "action": action,
        "owner_or_path": owner_or_path,
        "expected_outcome": expected_outcome,
        "related_evidence": related_evidence,
        "evaluation_available": source.get("evaluation_available"),
        "tact_spec_available": source.get("tact_spec_available"),
        "tact_spec_schema_version": source.get("tact_spec_schema_version"),
    }
    return {column: _csv_value(values.get(column)) for column in CSV_COLUMNS}


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _evidence_refs(unit: BuildableUnit, evidence: dict[str, Any]) -> list[str]:
    refs = [
        *[f"insight:{item}" for item in _string_list(evidence.get("insight_ids"))],
        *[f"signal:{item}" for item in _string_list(evidence.get("signal_ids"))],
        *[f"insight:{item}" for item in unit.inspiring_insights],
        *[f"signal:{item}" for item in unit.evidence_signals],
    ]
    return _dedupe(refs)


def _first_string(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            compact = _compact(item)
            if compact:
                return compact
    return _compact(value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    compact = _compact(value)
    return [compact] if compact else []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        compact = _compact(value)
        if not compact or compact in seen:
            continue
        seen.add(compact)
        result.append(compact)
    return result


def _join(values: Any) -> str:
    items = _string_list(values)
    return ", ".join(items) if items else "none"


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "; ".join(
            f"{_compact(key)}={_csv_value(item)}"
            for key, item in sorted(value.items())
            if _csv_value(item)
        )
    if isinstance(value, list):
        return "; ".join(_csv_value(item) for item in value if _csv_value(item))
    return _compact(value)
