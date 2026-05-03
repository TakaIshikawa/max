"""Generate deterministic migration checklists for buildable specs."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


MIGRATION_CHECKLIST_SCHEMA_VERSION = "max-migration-checklist/v1"
KIND = "max.migration_checklist"
MIGRATION_CHECKLIST_CSV_COLUMNS = (
    "schema_version",
    "kind",
    "idea_id",
    "source_status",
    "source_category",
    "tact_spec_schema_version",
    "migration_gate",
    "title",
    "workflow_context",
    "current_workaround",
    "recommendation",
    "phase",
    "item_type",
    "item_id",
    "item_name",
    "status",
    "owner",
    "priority",
    "dependency",
    "checklist_item",
    "rationale",
    "validation_evidence",
    "evidence_refs",
    "rollback_fallback_notes",
)


def generate_migration_checklist(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    tact_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn an idea, evaluation, and optional TactSpec into a migration checklist."""
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    problem = spec.get("problem") if isinstance(spec.get("problem"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}

    context = _context(unit, evaluation, spec, project, problem, solution, execution, evidence)
    gaps = _gaps(unit, evaluation, spec, context)
    assumptions = _assumptions(context, gaps)
    pre_tasks = _pre_migration_tasks(context)
    cutover_tasks = _cutover_tasks(context)
    rollback_checks = _rollback_checks(context, gaps)
    communications = _communications(context, gaps)

    return {
        "schema_version": MIGRATION_CHECKLIST_SCHEMA_VERSION,
        "kind": KIND,
        "idea_id": unit.id,
        "source": {
            "system": source.get("system") or "max",
            "type": source.get("type") or "idea",
            "idea_id": source.get("idea_id") or unit.id,
            "status": source.get("status") or unit.status,
            "domain": source.get("domain") or unit.domain,
            "category": str(source.get("category") or unit.category),
            "evaluation_available": evaluation is not None,
            "tact_spec_available": bool(spec),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
            "evidence_reference_count": len(context["evidence_references"]),
        },
        "idea": {
            "title": context["title"],
            "one_liner": context["one_liner"],
            "problem": context["problem"],
            "solution": context["solution"],
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "workflow_context": context["workflow_context"],
            "current_workaround": context["current_workaround"],
            "recommendation": context["recommendation"],
            "overall_score": context["overall_score"],
            "suggested_stack": context["suggested_stack"],
        },
        "summary": {
            "migration_gate": _migration_gate(evaluation, gaps),
            "assumption_count": len(assumptions),
            "pre_migration_task_count": len(pre_tasks),
            "cutover_task_count": len(cutover_tasks),
            "rollback_check_count": len(rollback_checks),
            "communication_count": len(communications),
            "gap_count": len(gaps),
        },
        "migration_assumptions": assumptions,
        "pre_migration_tasks": pre_tasks,
        "data_process_cutover_tasks": cutover_tasks,
        "rollback_checks": rollback_checks,
        "stakeholder_communications": communications,
        "evidence_references": context["evidence_references"],
        "unresolved_gaps": gaps,
        "missing_inputs": [gap["missing_input"] for gap in gaps],
    }


def render_migration_checklist_markdown(
    checklist: dict[str, Any], output_format: str = "markdown"
) -> str:
    """Render a generated migration checklist as deterministic Markdown."""
    if output_format != "markdown":
        raise ValueError(f"Unsupported migration checklist render format: {output_format}")

    idea = checklist.get("idea") or {}
    source = checklist.get("source") or {}
    summary = checklist.get("summary") or {}
    title = _text(idea.get("title")) or _text(checklist.get("idea_id")) or "Idea"

    lines = [
        f"# {title} Migration Checklist",
        "",
        f"- Schema version: {_text(checklist.get('schema_version'))}",
        f"- Kind: {_text(checklist.get('kind'))}",
        f"- Idea ID: {_text(checklist.get('idea_id'))}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- Category: {_text(source.get('category')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Evaluation available: {_text(source.get('evaluation_available'))}",
        f"- Migration gate: {_text(summary.get('migration_gate'))}",
        f"- Recommendation: {_text(idea.get('recommendation')) or 'none'}",
        f"- Workflow context: {_text(idea.get('workflow_context'))}",
        f"- Current workaround: {_text(idea.get('current_workaround'))}",
        "",
    ]

    one_liner = _text(idea.get("one_liner"))
    if one_liner:
        lines.extend([one_liner, ""])

    _extend_section(lines, "Assumptions", checklist.get("migration_assumptions") or [], _render_assumption)
    _extend_section(lines, "Pre-Migration Tasks", checklist.get("pre_migration_tasks") or [], _render_task)
    _extend_section(
        lines,
        "Data and Process Cutover",
        checklist.get("data_process_cutover_tasks") or [],
        _render_task,
    )
    _extend_section(lines, "Rollback", checklist.get("rollback_checks") or [], _render_rollback)
    _extend_section(
        lines,
        "Communications",
        checklist.get("stakeholder_communications") or [],
        _render_communication,
    )
    _extend_section(
        lines,
        "Evidence References",
        checklist.get("evidence_references") or [],
        _render_evidence,
        empty="No evidence references were provided.",
    )
    _extend_section(
        lines,
        "Gaps",
        checklist.get("unresolved_gaps") or [],
        _render_gap,
        empty="No unresolved migration gaps detected.",
    )

    return "\n".join(lines).rstrip() + "\n"


def render_migration_checklist_csv(checklist: dict[str, Any]) -> str:
    """Render a generated migration checklist as deterministic CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=MIGRATION_CHECKLIST_CSV_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _csv_rows(checklist or {}):
        writer.writerow(row)
    return output.getvalue()


def _context(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    spec: dict[str, Any],
    project: dict[str, Any],
    problem: dict[str, Any],
    solution: dict[str, Any],
    execution: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    workflow = _compact(project.get("workflow_context") or unit.workflow_context) or f"{unit.title} workflow"
    current_workaround = (
        _compact(problem.get("current_workaround") or unit.current_workaround)
        or "current manual or incumbent workflow"
    )
    suggested_stack = _suggested_stack(solution.get("suggested_stack") or unit.suggested_stack)
    risks = _list(execution.get("risks")) or list(unit.domain_risks)
    weaknesses = list(evaluation.weaknesses) if evaluation else []

    return {
        "title": _compact(project.get("title") or unit.title) or "Untitled idea",
        "one_liner": _compact(project.get("summary") or unit.one_liner),
        "problem": _compact(problem.get("statement") or unit.problem),
        "solution": _compact(solution.get("approach") or unit.solution),
        "technical_approach": _compact(solution.get("technical_approach") or unit.tech_approach),
        "target_user": _compact(project.get("specific_user") or unit.specific_user or project.get("target_users") or unit.target_users) or "target user",
        "buyer": _compact(project.get("buyer") or unit.buyer) or "migration sponsor",
        "workflow_context": workflow,
        "current_workaround": current_workaround,
        "value_proposition": _compact(project.get("value_proposition") or unit.value_proposition),
        "validation_plan": _compact(execution.get("validation_plan") or unit.validation_plan),
        "first_customers": _compact(execution.get("first_10_customers") or unit.first_10_customers) or "pilot users",
        "mvp_scope": _list(execution.get("mvp_scope")) or [item for item in (_compact(unit.solution), _compact(unit.tech_approach), _compact(unit.validation_plan)) if item],
        "suggested_stack": suggested_stack,
        "stack_label": _stack_label(suggested_stack),
        "recommendation": evaluation.recommendation if evaluation else None,
        "overall_score": evaluation.overall_score if evaluation else None,
        "risks": risks,
        "weaknesses": weaknesses,
        "lowest_confidence": _lowest_confidence_note(evaluation),
        "evidence_references": _evidence_references(unit, evidence),
        "tact_spec_available": bool(spec),
    }


def _assumptions(context: dict[str, Any], gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assumptions = [
        _assumption(
            "MA01",
            "Incumbent workflow",
            f"Migration replaces or augments {context['current_workaround']} in {context['workflow_context']}.",
            "high" if context["current_workaround"] != "current manual or incumbent workflow" else "low",
            ["unit.current_workaround", "project.workflow_context"],
        ),
        _assumption(
            "MA02",
            "Adoption audience",
            f"{context['target_user']} is the first migration audience and {context['buyer']} owns approval.",
            "medium",
            ["project.specific_user", "project.buyer"],
        ),
        _assumption(
            "MA03",
            "Technical path",
            f"Cutover can be rehearsed with {context['stack_label']} before broader rollout.",
            "medium" if context["stack_label"] != "unspecified stack" else "low",
            ["solution.suggested_stack", "solution.technical_approach"],
        ),
    ]
    if context["recommendation"]:
        assumptions.append(
            _assumption(
                "MA04",
                "Evaluation gate",
                f"Utility evaluation recommendation is {context['recommendation']}.",
                "high" if context["recommendation"] in {"strong_yes", "yes"} else "medium",
                ["evaluation.recommendation"],
            )
        )
    else:
        assumptions.append(
            _assumption(
                "MA04",
                "Evaluation gate",
                "No utility evaluation was provided; migration should stay reversible until review is complete.",
                "low",
                ["GAP01"],
            )
        )
    if gaps:
        assumptions.append(
            _assumption(
                "MA05",
                "Open migration inputs",
                f"{len(gaps)} migration input gap(s) must be closed or explicitly accepted before broad cutover.",
                "medium",
                [gap["id"] for gap in gaps],
            )
        )
    return assumptions


def _pre_migration_tasks(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _task(
            "PM01",
            "migration_owner",
            "Map the incumbent workflow, owners, handoffs, and stop conditions before changing production behavior.",
            context["current_workaround"],
            "Incumbent workflow map includes owner, users, data touched, and known failure modes.",
            ["unit.problem", "unit.current_workaround"],
        ),
        _task(
            "PM02",
            "engineering_owner",
            "Prepare a staging or pilot environment that mirrors the migration path and suggested stack.",
            context["stack_label"],
            "Pilot environment can run the new workflow without affecting incumbent production users.",
            ["solution.suggested_stack", "solution.technical_approach"],
        ),
        _task(
            "PM03",
            "product_owner",
            "Define success metrics and acceptance checks for the first migrated users.",
            context["validation_plan"] or context["value_proposition"] or "No validation plan supplied.",
            "Acceptance checks include baseline, target, measurement owner, and review date.",
            ["execution.validation_plan", "project.value_proposition"],
        ),
        _task(
            "PM04",
            "risk_owner",
            "Resolve or accept migration-critical risks before scheduling cutover.",
            _join(context["risks"] + context["weaknesses"], "No risks or weaknesses were provided."),
            "Risk register records mitigation, owner, and explicit go/no-go decision.",
            ["execution.risks", "evaluation.weaknesses"],
        ),
    ]


def _cutover_tasks(context: dict[str, Any]) -> list[dict[str, Any]]:
    mvp_scope = _join(context["mvp_scope"], context["solution"] or context["title"])
    return [
        _task(
            "CT01",
            "data_owner",
            "Inventory records, files, permissions, and generated outputs that must move or stay behind.",
            context["problem"],
            "Data inventory marks migrate, archive, delete, and no-migration categories.",
            ["problem.statement", "evidence.signal_ids"],
        ),
        _task(
            "CT02",
            "process_owner",
            "Run the new workflow in parallel with the incumbent path for representative pilot users.",
            f"Pilot users: {context['first_customers']}.",
            "Parallel run compares outputs, completion time, support load, and user-visible defects.",
            ["execution.first_10_customers", "execution.validation_plan"],
        ),
        _task(
            "CT03",
            "engineering_owner",
            "Cut over only the approved MVP scope and leave deferred behavior on the incumbent workflow.",
            mvp_scope,
            "Cutover notes identify included workflow steps, deferred steps, and owner-approved exceptions.",
            ["execution.mvp_scope", "solution.approach"],
        ),
        _task(
            "CT04",
            "support_owner",
            "Verify user permissions, notifications, reporting, and support routing after cutover.",
            context["workflow_context"],
            "Post-cutover smoke test covers access, key workflow output, communications, and support escalation.",
            ["project.workflow_context", "solution.composability_notes"],
        ),
    ]


def _rollback_checks(context: dict[str, Any], gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _rollback(
            "RB01",
            "Incumbent workflow remains available until migrated users pass acceptance checks.",
            context["current_workaround"],
            "Return affected users to incumbent workflow and freeze additional cutovers.",
            ["unit.current_workaround", "execution.validation_plan"],
        ),
        _rollback(
            "RB02",
            "Data or process discrepancies can be detected before users rely on migrated output.",
            context["validation_plan"] or "No validation plan supplied.",
            "Stop write propagation, preserve evidence, and reconcile against the incumbent source of truth.",
            ["execution.validation_plan"],
        ),
        _rollback(
            "RB03",
            "Evaluation, risk, or evidence gaps have an owner before broad rollout.",
            _join([gap["category"] for gap in gaps], "No unresolved gaps detected."),
            "Keep migration in pilot and require sponsor sign-off before expanding scope.",
            [gap["id"] for gap in gaps] or ["summary.migration_gate"],
        ),
    ]


def _communications(context: dict[str, Any], gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _communication(
            "COM01",
            context["buyer"],
            "Cutover readiness decision",
            f"Summarize migration gate, recommendation {context['recommendation'] or 'none'}, and open gaps.",
            "before scheduling cutover",
            [gap["id"] for gap in gaps] or ["evaluation.recommendation"],
        ),
        _communication(
            "COM02",
            context["target_user"],
            "Pilot user change notice",
            f"Explain what changes in {context['workflow_context']}, how to report issues, and how rollback works.",
            "before pilot start",
            ["project.workflow_context", "unit.current_workaround"],
        ),
        _communication(
            "COM03",
            "support_owner",
            "Support and escalation brief",
            "Share known risks, fallback path, smoke checks, and the first-response owner.",
            "before first migrated user",
            ["execution.risks", "evaluation.weaknesses"],
        ),
    ]


def _gaps(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    spec: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if evaluation is None:
        gaps.append(_gap("GAP01", "missing_evaluation", "No utility evaluation is available for migration go/no-go.", "utility_evaluation"))
    if not spec:
        gaps.append(_gap("GAP02", "missing_tact_spec", "No TactSpec preview was provided; migration tasks use BuildableUnit fields only.", "tact_spec"))
    if not _compact(unit.workflow_context):
        gaps.append(_gap("GAP03", "missing_workflow_context", "Workflow context is missing; migration audience and process boundaries need confirmation.", "workflow_context"))
    if not _compact(unit.current_workaround):
        gaps.append(_gap("GAP04", "missing_current_workaround", "Current workaround or incumbent workflow is missing; rollback path needs confirmation.", "current_workaround"))
    if not context["risks"]:
        gaps.append(_gap("GAP05", "missing_risks", "No domain or execution risks were provided for migration review.", "domain_risks"))
    if not context["validation_plan"]:
        gaps.append(_gap("GAP06", "missing_validation_plan", "No validation plan is available for cutover acceptance checks.", "validation_plan"))
    if not context["evidence_references"]:
        gaps.append(_gap("GAP07", "missing_evidence_refs", "No insight, signal, source idea, or evidence references are attached.", "evidence_refs"))
    if not context["suggested_stack"]:
        gaps.append(_gap("GAP08", "missing_stack", "No suggested stack is available for migration environment planning.", "suggested_stack"))
    return gaps


def _migration_gate(evaluation: UtilityEvaluation | None, gaps: list[dict[str, Any]]) -> str:
    blocking = {gap["category"] for gap in gaps}
    if evaluation is None or "missing_tact_spec" in blocking:
        return "migration_inputs_required"
    if evaluation.recommendation in {"no", "strong_no"}:
        return "not_recommended_for_migration"
    if blocking:
        return "pilot_only_until_gaps_close"
    if evaluation.recommendation in {"strong_yes", "yes"}:
        return "ready_for_migration_review"
    return "needs_sponsor_review"


def _assumption(
    item_id: str, title: str, statement: str, confidence: str, evidence_refs: list[str]
) -> dict[str, Any]:
    return {
        "id": item_id,
        "title": title,
        "statement": _compact(statement),
        "confidence": confidence,
        "evidence_refs": evidence_refs,
    }


def _task(
    item_id: str,
    owner: str,
    task: str,
    rationale: str,
    evidence_required: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "status": "pending",
        "owner": owner,
        "task": _compact(task),
        "rationale": _compact(rationale),
        "evidence_required": evidence_required,
        "required": True,
        "evidence_refs": evidence_refs,
    }


def _rollback(
    item_id: str, check: str, trigger: str, response: str, evidence_refs: list[str]
) -> dict[str, Any]:
    return {
        "id": item_id,
        "status": "pending",
        "owner": "migration_owner",
        "check": _compact(check),
        "trigger": _compact(trigger),
        "response": _compact(response),
        "evidence_refs": evidence_refs,
    }


def _communication(
    item_id: str,
    audience: str,
    topic: str,
    message: str,
    timing: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "status": "pending",
        "audience": _compact(audience) or "stakeholder",
        "topic": topic,
        "message": _compact(message),
        "timing": timing,
        "evidence_refs": evidence_refs,
    }


def _gap(item_id: str, category: str, description: str, missing_input: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "category": category,
        "description": description,
        "missing_input": missing_input,
        "owner": "migration_owner",
        "resolution": "Confirm before broad migration or record explicit sponsor acceptance.",
    }


def _render_assumption(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('title'))}",
        "",
        f"- Statement: {_text(item.get('statement'))}",
        f"- Confidence: {_text(item.get('confidence'))}",
        f"- Evidence: {_inline_list(item.get('evidence_refs') or [])}",
        "",
    ]


def _render_task(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('task'))}",
        "",
        f"- Status: {_text(item.get('status'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Required: {_text(item.get('required'))}",
        f"- Rationale: {_text(item.get('rationale'))}",
        f"- Evidence required: {_text(item.get('evidence_required'))}",
        f"- Evidence: {_inline_list(item.get('evidence_refs') or [])}",
        "",
    ]


def _render_rollback(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('check'))}",
        "",
        f"- Status: {_text(item.get('status'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Trigger: {_text(item.get('trigger'))}",
        f"- Response: {_text(item.get('response'))}",
        f"- Evidence: {_inline_list(item.get('evidence_refs') or [])}",
        "",
    ]


def _render_communication(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('topic'))}",
        "",
        f"- Audience: {_text(item.get('audience'))}",
        f"- Timing: {_text(item.get('timing'))}",
        f"- Message: {_text(item.get('message'))}",
        f"- Evidence: {_inline_list(item.get('evidence_refs') or [])}",
        "",
    ]


def _render_evidence(item: dict[str, Any]) -> list[str]:
    return [
        f"- `{_text(item.get('id'))}` ({_text(item.get('type'))}): {_text(item.get('source'))}",
    ]


def _render_gap(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('category'))}",
        "",
        f"- Missing input: {_text(item.get('missing_input'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Resolution: {_text(item.get('resolution'))}",
        "",
    ]


def _csv_rows(checklist: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for item in _dict_items(checklist.get("migration_assumptions")):
        rows.append(
            _csv_row(
                checklist,
                phase="assumptions",
                item_type="assumption",
                item_id=item.get("id"),
                item_name=item.get("title"),
                priority=item.get("confidence"),
                checklist_item=item.get("statement"),
                validation_evidence=item.get("confidence"),
                evidence_refs=item.get("evidence_refs"),
            )
        )

    for phase, items in (
        ("pre_migration", checklist.get("pre_migration_tasks")),
        ("data_process_cutover", checklist.get("data_process_cutover_tasks")),
    ):
        for item in _dict_items(items):
            rows.append(
                _csv_row(
                    checklist,
                    phase=phase,
                    item_type="task",
                    item_id=item.get("id"),
                    status=item.get("status"),
                    owner=item.get("owner"),
                    priority="required" if item.get("required") is True else "",
                    dependency=item.get("rationale"),
                    checklist_item=item.get("task"),
                    rationale=item.get("rationale"),
                    validation_evidence=item.get("evidence_required"),
                    evidence_refs=item.get("evidence_refs"),
                )
            )

    for item in _dict_items(checklist.get("rollback_checks")):
        rows.append(
            _csv_row(
                checklist,
                phase="rollback",
                item_type="rollback_check",
                item_id=item.get("id"),
                status=item.get("status"),
                owner=item.get("owner"),
                dependency=item.get("trigger"),
                checklist_item=item.get("check"),
                validation_evidence=item.get("trigger"),
                evidence_refs=item.get("evidence_refs"),
                rollback_fallback_notes=item.get("response"),
            )
        )

    for item in _dict_items(checklist.get("stakeholder_communications")):
        rows.append(
            _csv_row(
                checklist,
                phase="communications",
                item_type="communication",
                item_id=item.get("id"),
                item_name=item.get("topic"),
                status=item.get("status"),
                owner=item.get("audience"),
                dependency=item.get("timing"),
                checklist_item=item.get("message"),
                validation_evidence=item.get("timing"),
                evidence_refs=item.get("evidence_refs"),
            )
        )

    for item in _dict_items(checklist.get("unresolved_gaps")):
        rows.append(
            _csv_row(
                checklist,
                phase="gaps",
                item_type="gap",
                item_id=item.get("id"),
                item_name=item.get("category"),
                owner=item.get("owner"),
                priority="open",
                dependency=item.get("missing_input"),
                checklist_item=item.get("description"),
                validation_evidence=item.get("missing_input"),
                rollback_fallback_notes=item.get("resolution"),
            )
        )

    return rows


def _csv_row(
    checklist: dict[str, Any],
    *,
    phase: str,
    item_type: str,
    item_id: Any = None,
    item_name: Any = None,
    status: Any = None,
    owner: Any = None,
    priority: Any = None,
    dependency: Any = None,
    checklist_item: Any = None,
    rationale: Any = None,
    validation_evidence: Any = None,
    evidence_refs: Any = None,
    rollback_fallback_notes: Any = None,
) -> dict[str, str]:
    source = checklist.get("source") if isinstance(checklist.get("source"), dict) else {}
    idea = checklist.get("idea") if isinstance(checklist.get("idea"), dict) else {}
    summary = checklist.get("summary") if isinstance(checklist.get("summary"), dict) else {}
    values = {
        "schema_version": checklist.get("schema_version"),
        "kind": checklist.get("kind"),
        "idea_id": checklist.get("idea_id"),
        "source_status": source.get("status"),
        "source_category": source.get("category"),
        "tact_spec_schema_version": source.get("tact_spec_schema_version"),
        "migration_gate": summary.get("migration_gate"),
        "title": idea.get("title"),
        "workflow_context": idea.get("workflow_context"),
        "current_workaround": idea.get("current_workaround"),
        "recommendation": idea.get("recommendation"),
        "phase": phase,
        "item_type": item_type,
        "item_id": item_id,
        "item_name": item_name,
        "status": status,
        "owner": owner,
        "priority": priority,
        "dependency": dependency,
        "checklist_item": checklist_item,
        "rationale": rationale,
        "validation_evidence": validation_evidence,
        "evidence_refs": evidence_refs,
        "rollback_fallback_notes": rollback_fallback_notes,
    }
    return {column: _csv_text(values.get(column)) for column in MIGRATION_CHECKLIST_CSV_COLUMNS}


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _extend_section(
    lines: list[str],
    title: str,
    items: list[Any],
    renderer,
    empty: str = "No items.",
) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend([empty, ""])
        return
    for item in items:
        lines.extend(renderer(item))


def _evidence_references(unit: BuildableUnit, evidence: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for value in _list(evidence.get("insight_ids")) or unit.inspiring_insights:
        refs.append({"id": f"insight:{value}", "type": "insight", "source": str(value)})
    for value in _list(evidence.get("signal_ids")) or unit.evidence_signals:
        refs.append({"id": f"signal:{value}", "type": "signal", "source": str(value)})
    for value in _list(evidence.get("source_idea_ids")) or unit.source_idea_ids:
        refs.append({"id": f"idea:{value}", "type": "source_idea", "source": str(value)})
    rationale = _compact(evidence.get("rationale") or unit.evidence_rationale)
    if rationale:
        refs.append({"id": "evidence:rationale", "type": "rationale", "source": rationale})
    return refs


def _suggested_stack(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _compact(raw) for key, raw in sorted(value.items()) if _compact(raw)}


def _stack_label(stack: dict[str, str]) -> str:
    values = [f"{key}={value}" for key, value in stack.items()]
    return ", ".join(values) if values else "unspecified stack"


def _lowest_confidence_note(evaluation: UtilityEvaluation | None) -> str:
    if evaluation is None:
        return "No evaluation is available."
    names = (
        "pain_severity",
        "addressable_scale",
        "build_effort",
        "composability",
        "competitive_density",
        "timing_fit",
        "compounding_value",
    )
    name, score = min(((name, getattr(evaluation, name)) for name in names), key=lambda item: (item[1].confidence, item[0]))
    return f"{name.replace('_', ' ')}: confidence {score.confidence:.2f}; {score.reasoning}"


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    if isinstance(value, tuple):
        return [_compact(item) for item in value if _compact(item)]
    if _compact(value):
        return [_compact(value)]
    return []


def _join(items: list[str], empty: str) -> str:
    compacted = [_compact(item) for item in items if _compact(item)]
    return "; ".join(compacted) if compacted else empty


def _inline_list(items: list[Any]) -> str:
    values = [_compact(item) for item in items if _compact(item)]
    return ", ".join(values) if values else "none"


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "; ".join(
            f"{_csv_text(key)}={_csv_text(item)}"
            for key, item in sorted(value.items())
            if _csv_text(item)
        )
    if isinstance(value, list | tuple | set):
        values = sorted(value, key=str) if isinstance(value, set) else value
        return "; ".join(_csv_text(item) for item in values if _csv_text(item))
    return _compact(value)


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
