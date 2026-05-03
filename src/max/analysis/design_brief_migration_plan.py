"""Deterministic migration plans for persisted design briefs."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.migration_plan"
SCHEMA_VERSION = "max.design_brief.migration_plan.v1"
CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "phase_sequence",
    "phase_type",
    "phase_name",
    "row_type",
    "item_id",
    "task",
    "dependency",
    "owner",
    "validation",
    "rollback_note",
    "timing",
    "evidence_reference_ids",
    "source_idea_ids",
)

PHASES: tuple[str, ...] = (
    "preparation",
    "data_workflow_migration",
    "pilot_rollout",
    "broad_rollout",
    "rollback",
)

_INTEGRATION_RISK_TERMS = (
    "api",
    "credential",
    "data",
    "integration",
    "legacy",
    "migration",
    "privacy",
    "security",
    "sync",
)


def build_design_brief_migration_plan(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a workflow migration plan from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _migration_context(design_brief, source_ideas, lead_idea)
    evidence = _evidence_references(design_brief, source_ideas)
    owner_roles = _owner_roles(context)
    integration_risks = _integration_risks(design_brief, source_ideas, source_idea_ids)
    data_steps = _data_workflow_migration_steps(context, source_idea_ids)
    rollback_criteria = _rollback_criteria(context, integration_risks, source_idea_ids)
    training = _training_touchpoints(context, source_idea_ids)
    phases = _migration_phases(
        context,
        data_steps,
        rollback_criteria,
        training,
        integration_risks,
        source_idea_ids,
    )
    warnings = _validation_warnings(design_brief, context, evidence, source_idea_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": design_brief.get("updated_at") or design_brief.get("created_at"),
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
        },
        "summary": {
            "migration_goal": f"Move {context['target_user']} from {context['incumbent_workflow']} to {context['product_concept']}.",
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "workflow_context": context["workflow_context"],
            "incumbent_workflow": context["incumbent_workflow"],
            "fallbacks_used": context["fallbacks_used"],
            "phase_count": len(phases),
            "data_workflow_step_count": len(data_steps),
            "rollback_criterion_count": len(rollback_criteria),
            "training_touchpoint_count": len(training),
            "integration_risk_count": len(integration_risks),
            "validation_warning_count": len(warnings),
        },
        "owner_roles": owner_roles,
        "migration_phases": phases,
        "data_workflow_migration_steps": data_steps,
        "rollback_criteria": rollback_criteria,
        "training_touchpoints": training,
        "integration_risks": integration_risks,
        "evidence_references": evidence,
        "validation_warnings": warnings,
        "source_ideas": source_ideas,
    }


def render_design_brief_migration_plan(report: dict[str, Any], fmt: str = "json") -> str:
    """Render a migration plan as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_design_brief_migration_plan_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported migration plan format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Migration Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {', '.join(brief.get('source_idea_ids') or []) or 'design brief'}",
        "",
        "## Migration Summary",
        "",
        f"- Goal: {summary['migration_goal']}",
        f"- Target user: {summary['target_user']}",
        f"- Buyer: {summary['buyer']}",
        f"- Workflow: {summary['workflow_context']}",
        f"- Incumbent workflow: {summary['incumbent_workflow']}",
        f"- Fallbacks used: {', '.join(summary['fallbacks_used']) or 'none'}",
        "",
        "## Owner Roles",
        "",
    ]

    for role in report["owner_roles"]:
        lines.extend(
            [
                f"### {role['role']}",
                "",
                f"- Responsibility: {role['responsibility']}",
                f"- Decision rights: {role['decision_rights']}",
                "",
            ]
        )

    lines.extend(["## Migration Phases", ""])
    for phase in report["migration_phases"]:
        lines.extend(
            [
                f"### {phase['sequence']}. {phase['name']}",
                "",
                f"- Phase type: {phase['phase_type']}",
                f"- Objective: {phase['objective']}",
                f"- Owner: {phase['owner']}",
                f"- Source idea references: {', '.join(phase['source_idea_ids']) or 'design brief'}",
                "- Tasks:",
            ]
        )
        for task in phase["tasks"]:
            lines.append(f"  - {task}")
        lines.append("- Acceptance checks:")
        for check in phase["acceptance_checks"]:
            lines.append(f"  - {check}")
        lines.append("- Risks:")
        for risk in phase["risks"]:
            lines.append(f"  - {risk}")
        lines.append("")

    lines.extend(["## Data and Workflow Migration Steps", ""])
    for step in report["data_workflow_migration_steps"]:
        lines.extend(
            [
                f"### {step['id']}: {step['name']}",
                "",
                f"- Owner: {step['owner']}",
                f"- Migration action: {step['migration_action']}",
                f"- Validation: {step['validation']}",
                f"- Source idea references: {', '.join(step['source_idea_ids']) or 'design brief'}",
                "",
            ]
        )

    lines.extend(["## Rollback Criteria", ""])
    for criterion in report["rollback_criteria"]:
        lines.extend(
            [
                f"- **{criterion['id']}** ({criterion['severity']}): {criterion['trigger']}",
                f"  Response: {criterion['response']}",
                f"  Owner: {criterion['owner']}",
            ]
        )

    lines.extend(["", "## Training Touchpoints", ""])
    for touchpoint in report["training_touchpoints"]:
        lines.extend(
            [
                f"- **{touchpoint['id']} {touchpoint['audience']}** ({touchpoint['timing']}): {touchpoint['content']}",
                f"  Owner: {touchpoint['owner']}",
            ]
        )

    lines.extend(["", "## Integration Risks", ""])
    for risk in report["integration_risks"]:
        lines.extend(
            [
                f"- **{risk['id']}** ({risk['severity']}): {risk['risk']}",
                f"  Mitigation: {risk['mitigation']}",
            ]
        )

    lines.extend(["", "## Evidence References", ""])
    if report["evidence_references"]:
        for item in report["evidence_references"]:
            lines.append(f"- **{item['id']}** ({item['type']}): {item['summary']}")
    else:
        lines.append("- None")

    lines.extend(["", "## Validation Warnings", ""])
    if report["validation_warnings"]:
        for warning in report["validation_warnings"]:
            lines.extend(
                [
                    f"- **{warning['id']} {warning['field']}** ({warning['severity']}): {warning['warning']}",
                    f"  Validation needed: {warning['validation_needed']}",
                ]
            )
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def render_design_brief_migration_plan_csv(report: dict[str, Any]) -> str:
    """Render deterministic migration plan rows for spreadsheet tracking."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def migration_plan_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    """Return a stable filename for a migration plan export."""
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    brief_id = _filename_part(str(design_brief.get("id") or "design-brief"))
    title = _filename_part(str(design_brief.get("title") or "migration-plan"))
    return f"{brief_id}-{title}-migration-plan.{extension}"


def _csv_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    phases = _phase_items_for_csv(report)
    if not phases:
        return rows

    evidence = _evidence_references_by_source(report)
    previous_phase_task_id = ""
    for phase in phases:
        phase_task_ids: list[str] = []
        phase_id = _csv_text(phase.get("id")) or f"MP{_csv_text(phase.get('sequence'))}"
        for index, task in enumerate(_csv_item_list(phase.get("tasks")), start=1):
            item_id = f"{phase_id}-T{index}"
            dependency = phase_task_ids[-1] if phase_task_ids else previous_phase_task_id
            rows.append(
                _csv_row(
                    report,
                    phase,
                    "phase_task",
                    item_id,
                    task,
                    dependency,
                    phase.get("owner"),
                    phase.get("acceptance_checks"),
                    _phase_rollback_note(report, phase),
                    f"phase {phase.get('sequence') or ''}".strip(),
                    evidence,
                )
            )
            phase_task_ids.append(item_id)
        if phase_task_ids:
            previous_phase_task_id = phase_task_ids[-1]

    rows.extend(_data_workflow_csv_rows(report, phases, evidence))
    rows.extend(_training_csv_rows(report, phases, evidence))
    rows.extend(_rollback_csv_rows(report, phases, evidence))
    return rows


def _data_workflow_csv_rows(
    report: dict[str, Any],
    phases: list[dict[str, Any]],
    evidence: dict[str, list[str]],
) -> list[dict[str, str]]:
    phase = _phase_by_type(phases, "data_workflow_migration")
    rows: list[dict[str, str]] = []
    for index, step in enumerate(_dict_items(report.get("data_workflow_migration_steps")), start=1):
        rows.append(
            _csv_row(
                report,
                phase,
                "data_workflow_step",
                step.get("id") or f"DWM{index}",
                step.get("migration_action") or step.get("name"),
                f"{phase.get('id')}-T1" if phase.get("id") else "",
                step.get("owner"),
                step.get("validation"),
                "",
                "data and workflow migration",
                evidence,
                step.get("source_idea_ids"),
            )
        )
    return rows


def _training_csv_rows(
    report: dict[str, Any],
    phases: list[dict[str, Any]],
    evidence: dict[str, list[str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, touchpoint in enumerate(_dict_items(report.get("training_touchpoints")), start=1):
        timing = _csv_text(touchpoint.get("timing"))
        phase_type = "broad_rollout" if "broad" in timing.lower() else "pilot_rollout"
        rows.append(
            _csv_row(
                report,
                _phase_by_type(phases, phase_type),
                "training_touchpoint",
                touchpoint.get("id") or f"TR{index}",
                touchpoint.get("content"),
                "",
                touchpoint.get("owner"),
                f"Audience: {touchpoint.get('audience') or ''}".strip(),
                "",
                timing,
                evidence,
                touchpoint.get("source_idea_ids"),
            )
        )
    return rows


def _rollback_csv_rows(
    report: dict[str, Any],
    phases: list[dict[str, Any]],
    evidence: dict[str, list[str]],
) -> list[dict[str, str]]:
    phase = _phase_by_type(phases, "rollback")
    rows: list[dict[str, str]] = []
    for index, criterion in enumerate(_dict_items(report.get("rollback_criteria")), start=1):
        rows.append(
            _csv_row(
                report,
                phase,
                "rollback_criterion",
                criterion.get("id") or f"RB{index}",
                criterion.get("trigger"),
                f"{phase.get('id')}-T1" if phase.get("id") else "",
                criterion.get("owner"),
                criterion.get("severity"),
                criterion.get("response"),
                "rollback trigger",
                evidence,
                criterion.get("source_idea_ids"),
            )
        )
    return rows


def _csv_row(
    report: dict[str, Any],
    phase: dict[str, Any],
    row_type: str,
    item_id: Any,
    task: Any,
    dependency: Any,
    owner: Any,
    validation: Any,
    rollback_note: Any,
    timing: Any,
    evidence: dict[str, list[str]],
    source_idea_ids: Any | None = None,
) -> dict[str, str]:
    brief = report.get("design_brief") or {}
    source_ids = _string_list(
        source_idea_ids if source_idea_ids is not None else phase.get("source_idea_ids")
    )
    values = {
        "design_brief_id": brief.get("id") or report.get("brief_id"),
        "design_brief_title": brief.get("title") or report.get("title"),
        "phase_sequence": phase.get("sequence"),
        "phase_type": phase.get("phase_type"),
        "phase_name": phase.get("name"),
        "row_type": row_type,
        "item_id": item_id,
        "task": task,
        "dependency": dependency,
        "owner": owner,
        "validation": validation,
        "rollback_note": rollback_note,
        "timing": timing,
        "evidence_reference_ids": _evidence_ids_for_sources(evidence, source_ids),
        "source_idea_ids": source_ids,
    }
    return {column: _csv_text(values.get(column)) for column in CSV_COLUMNS}


def _phase_items_for_csv(report: dict[str, Any]) -> list[dict[str, Any]]:
    phases = report.get("migration_phases") or report.get("phases") or []
    if isinstance(phases, dict):
        phases = phases.get("items") or phases.get("phases") or []
    if not isinstance(phases, list):
        return []
    return [phase for phase in phases if isinstance(phase, dict)]


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("items") or value.get("rows") or []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _csv_item_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, set):
        value = sorted(value, key=str)
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item)]
    return [str(value)] if str(value) else []


def _phase_by_type(phases: list[dict[str, Any]], phase_type: str) -> dict[str, Any]:
    return next((phase for phase in phases if phase.get("phase_type") == phase_type), {})


def _phase_rollback_note(report: dict[str, Any], phase: dict[str, Any]) -> str:
    if phase.get("phase_type") != "rollback":
        return ""
    return _csv_text(
        [criterion.get("response") for criterion in _dict_items(report.get("rollback_criteria"))]
    )


def _evidence_references_by_source(report: dict[str, Any]) -> dict[str, list[str]]:
    evidence_by_source: dict[str, list[str]] = {}
    for item in _dict_items(report.get("evidence_references")):
        item_id = _csv_text(item.get("id"))
        if not item_id:
            continue
        source_ids = _string_list(item.get("source_idea_ids"))
        if not source_ids:
            evidence_by_source.setdefault("", []).append(item_id)
        for source_id in source_ids:
            evidence_by_source.setdefault(source_id, []).append(item_id)
    return {
        source_id: list(dict.fromkeys(ids))
        for source_id, ids in sorted(evidence_by_source.items(), key=lambda item: item[0])
    }


def _evidence_ids_for_sources(evidence: dict[str, list[str]], source_ids: list[str]) -> list[str]:
    ids: list[str] = []
    ids.extend(evidence.get("", []))
    for source_id in source_ids:
        ids.extend(evidence.get(source_id, []))
    return list(dict.fromkeys(ids))


def _migration_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    lead_idea: dict[str, Any] | None,
) -> dict[str, Any]:
    fallbacks: list[str] = []
    title = _first_text(design_brief.get("title"), "Untitled design brief")
    target_user = _first_with_label(
        fallbacks,
        "specific_user",
        (design_brief.get("specific_user"), "design_brief.specific_user"),
        (lead_idea and lead_idea.get("specific_user"), "lead_idea.specific_user"),
        (_field_values(source_ideas, "specific_user"), "source_ideas.specific_user"),
        (f"{title} user", "explicit_fallback"),
    )
    buyer = _first_with_label(
        fallbacks,
        "buyer",
        (design_brief.get("buyer"), "design_brief.buyer"),
        (lead_idea and lead_idea.get("buyer"), "lead_idea.buyer"),
        (_field_values(source_ideas, "buyer"), "source_ideas.buyer"),
        ("workflow owner", "explicit_fallback"),
    )
    workflow = _first_with_label(
        fallbacks,
        "workflow_context",
        (design_brief.get("workflow_context"), "design_brief.workflow_context"),
        (lead_idea and lead_idea.get("workflow_context"), "lead_idea.workflow_context"),
        (_field_values(source_ideas, "workflow_context"), "source_ideas.workflow_context"),
        (f"{title} workflow", "explicit_fallback"),
    )
    incumbent = _first_with_label(
        fallbacks,
        "current_workaround",
        (design_brief.get("current_workaround"), "design_brief.current_workaround"),
        (lead_idea and lead_idea.get("current_workaround"), "lead_idea.current_workaround"),
        (_field_values(source_ideas, "current_workaround"), "source_ideas.current_workaround"),
        ("current manual or incumbent workflow", "explicit_fallback"),
    )
    product_concept = _first_text(
        design_brief.get("merged_product_concept"),
        lead_idea and lead_idea.get("solution"),
        f"{title} target workflow",
    )
    scope = _string_list(design_brief.get("mvp_scope"))
    milestones = _string_list(design_brief.get("first_milestones"))
    validation_plan = _first_text(
        design_brief.get("validation_plan"),
        lead_idea and lead_idea.get("validation_plan"),
        "Run an operational acceptance review before expanding migration.",
    )
    return {
        "title": title,
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "incumbent_workflow": incumbent,
        "product_concept": product_concept,
        "primary_scope": scope[0] if scope else f"first usable {title} workflow",
        "secondary_scope": scope[1] if len(scope) > 1 else "workflow handoff and support path",
        "first_milestone": milestones[0] if milestones else "complete a controlled pilot migration",
        "validation_plan": validation_plan,
        "fallbacks_used": fallbacks,
    }


def _owner_roles(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "role": "Product owner",
            "responsibility": f"Own migration scope, acceptance checks, and proceed or rollback decisions for {context['product_concept']}.",
            "decision_rights": "Can approve pilot entry, broad rollout entry, and rollback activation.",
        },
        {
            "role": "Workflow owner",
            "responsibility": f"Confirm that {context['workflow_context']} remains operable during transition from {context['incumbent_workflow']}.",
            "decision_rights": "Can block rollout when operational continuity is not proven.",
        },
        {
            "role": "Engineering owner",
            "responsibility": "Own integration readiness, data checks, migration scripts, feature flags, and rollback mechanics.",
            "decision_rights": "Can pause migration when telemetry, data quality, or integration checks fail.",
        },
        {
            "role": "Enablement owner",
            "responsibility": f"Train {context['target_user']} and support teams before each migration expansion.",
            "decision_rights": "Can require additional training before adding new cohorts.",
        },
    ]


def _migration_phases(
    context: dict[str, Any],
    data_steps: list[dict[str, Any]],
    rollback_criteria: list[dict[str, Any]],
    training: list[dict[str, Any]],
    integration_risks: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    data_task = data_steps[0]["migration_action"]
    training_task = training[0]["content"]
    rollback_trigger = rollback_criteria[0]["trigger"]
    primary_risk = integration_risks[0]["risk"]
    return [
        _phase(
            1,
            "preparation",
            "Preparation and migration readiness",
            f"Baseline the incumbent workflow and define controlled migration gates for {context['product_concept']}.",
            "Product owner",
            [
                f"Inventory current users, data, integrations, and decisions in {context['incumbent_workflow']}.",
                f"Define pilot cohort and success checks for {context['primary_scope']}.",
                "Publish owner roster, support path, and go/no-go calendar.",
            ],
            [
                "Pilot cohort, acceptance checks, and rollback authority are documented.",
                "Incumbent workflow remains available for the pilot cohort.",
                f"Validation plan is mapped to migration gates: {context['validation_plan']}",
            ],
            [
                "Hidden dependencies in the incumbent workflow may be missed.",
                primary_risk,
            ],
            source_idea_ids,
        ),
        _phase(
            2,
            "data_workflow_migration",
            "Data and workflow migration",
            "Move the smallest useful workflow slice while preserving auditability and operating continuity.",
            "Engineering owner",
            [
                data_task,
                f"Configure workflow handoff for {context['workflow_context']}.",
                "Run side-by-side reconciliation against the incumbent workflow.",
            ],
            [
                "Migrated records reconcile with source records or documented exceptions.",
                "Users can complete the target workflow without losing incumbent status.",
                "Telemetry, support queue, and rollback switch are active.",
            ],
            [
                "Data mapping or integration assumptions may be incomplete.",
                "Side-by-side operation may create duplicate work without clear ownership.",
            ],
            source_idea_ids,
        ),
        _phase(
            3,
            "pilot_rollout",
            "Pilot rollout",
            f"Shift a bounded cohort of {context['target_user']} to the new workflow and monitor adoption evidence.",
            "Workflow owner",
            [
                training_task,
                f"Activate pilot users for {context['primary_scope']}.",
                "Review support tickets, telemetry, and workflow completion daily.",
            ],
            [
                f"Pilot users complete {context['primary_scope']} with acceptable support load.",
                "No critical rollback criterion has been met.",
                "Workflow owner signs off on expanding beyond the pilot cohort.",
            ],
            [
                "Pilot users may revert to the incumbent workflow without reporting blockers.",
                "Support load may exceed the capacity planned for rollout.",
            ],
            source_idea_ids,
        ),
        _phase(
            4,
            "broad_rollout",
            "Broad rollout",
            f"Expand migration after pilot evidence confirms {context['first_milestone']}.",
            "Product owner",
            [
                "Move additional cohorts in scheduled batches.",
                f"Retire duplicate steps for {context['secondary_scope']} only after acceptance checks pass.",
                "Publish adoption, support, and rollback status to stakeholders.",
            ],
            [
                "Batch migration metrics stay within pilot guardrails.",
                "Support and enablement materials cover repeated questions.",
                "Incumbent workflow retirement has an owner and exception process.",
            ],
            [
                "Batch expansion can amplify unresolved integration defects.",
                "Retiring old workflow steps too early can break exceptions or edge cases.",
            ],
            source_idea_ids,
        ),
        _phase(
            5,
            "rollback",
            "Rollback and stabilization",
            "Preserve a clear path back to the incumbent workflow when migration guardrails fail.",
            "Engineering owner",
            [
                f"Activate rollback when triggered: {rollback_trigger}",
                "Restore affected users to the incumbent workflow and freeze additional cohorts.",
                "Record root cause, customer impact, data corrections, and revised go-forward gate.",
            ],
            [
                "Affected users can complete critical work in the incumbent workflow.",
                "Data corrections are reconciled and reviewed by the workflow owner.",
                "Restart criteria are documented before rollout resumes.",
            ],
            [
                "Rollback can create divergent records without reconciliation ownership.",
                "A rollback without clear communications can reduce trust in the migrated workflow.",
            ],
            source_idea_ids,
        ),
    ]


def _phase(
    sequence: int,
    phase_type: str,
    name: str,
    objective: str,
    owner: str,
    tasks: list[str],
    acceptance_checks: list[str],
    risks: list[str],
    source_idea_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": f"MP{sequence}",
        "sequence": sequence,
        "phase_type": phase_type,
        "name": name,
        "objective": objective,
        "owner": owner,
        "tasks": tasks,
        "acceptance_checks": acceptance_checks,
        "risks": risks,
        "source_idea_ids": source_idea_ids,
    }


def _data_workflow_migration_steps(
    context: dict[str, Any], source_idea_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "id": "DWM1",
            "name": "Workflow inventory and mapping",
            "owner": "Workflow owner",
            "migration_action": f"Map each step in {context['incumbent_workflow']} to the target {context['workflow_context']} path.",
            "validation": "Every critical step has a keep, replace, automate, or retire decision.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "DWM2",
            "name": "Data readiness and reconciliation",
            "owner": "Engineering owner",
            "migration_action": f"Identify records, permissions, and status fields needed to support {context['primary_scope']}.",
            "validation": "Sample migrated records match source records, permissions, and workflow status.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "DWM3",
            "name": "Parallel run and cutover gate",
            "owner": "Product owner",
            "migration_action": "Run the migrated workflow beside the incumbent path for the pilot cohort before retiring duplicated steps.",
            "validation": "Pilot cohort completes the workflow with documented exceptions and no unresolved severity-high defects.",
            "source_idea_ids": source_idea_ids,
        },
    ]


def _rollback_criteria(
    context: dict[str, Any],
    integration_risks: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    risk = integration_risks[0]["risk"] if integration_risks else "Critical migration guardrail fails."
    return [
        {
            "id": "RB1",
            "severity": "critical",
            "trigger": f"{context['target_user']} cannot complete {context['primary_scope']} in the new workflow.",
            "response": f"Return affected users to {context['incumbent_workflow']} and freeze cohort expansion.",
            "owner": "Workflow owner",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "RB2",
            "severity": "high",
            "trigger": "Migrated data, permissions, or status fields fail reconciliation.",
            "response": "Stop migration jobs, correct records, and rerun reconciliation before resuming.",
            "owner": "Engineering owner",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "RB3",
            "severity": "high",
            "trigger": risk,
            "response": "Escalate to the product owner and require an updated mitigation before the next cohort.",
            "owner": "Product owner",
            "source_idea_ids": source_idea_ids,
        },
    ]


def _training_touchpoints(
    context: dict[str, Any], source_idea_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "id": "TR1",
            "audience": context["target_user"],
            "timing": "before pilot activation",
            "content": f"Train pilot users on completing {context['primary_scope']} and when to use the incumbent workflow fallback.",
            "owner": "Enablement owner",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "TR2",
            "audience": "support and operations",
            "timing": "during pilot",
            "content": "Review known migration blockers, escalation rules, rollback triggers, and exception logging.",
            "owner": "Workflow owner",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "TR3",
            "audience": context["buyer"],
            "timing": "before broad rollout",
            "content": "Review rollout evidence, business impact, unresolved risks, and the retirement plan for incumbent workflow steps.",
            "owner": "Product owner",
            "source_idea_ids": source_idea_ids,
        },
    ]


def _integration_risks(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    risks = _dedupe_strings(
        [
            *_string_list(design_brief.get("risks")),
            *_field_values(source_ideas, "domain_risks"),
        ]
    )
    integration_risks = [
        risk
        for risk in risks
        if any(term in risk.lower() for term in _INTEGRATION_RISK_TERMS)
    ]
    if not integration_risks:
        integration_risks = risks[:2]
    if not integration_risks:
        integration_risks = [
            "Workflow dependencies, data quality, or integration ownership may be under-specified."
        ]

    return [
        {
            "id": f"IR{index}",
            "risk": risk,
            "severity": _risk_severity(risk),
            "mitigation": _risk_mitigation(risk),
            "source_idea_ids": _source_ids_for_text(risk, source_ideas, source_idea_ids),
        }
        for index, risk in enumerate(integration_risks[:4], start=1)
    ]


def _risk_severity(risk: str) -> str:
    lowered = risk.lower()
    if any(term in lowered for term in ("security", "privacy", "credential", "compliance")):
        return "high"
    if any(term in lowered for term in ("data", "integration", "migration", "sync")):
        return "medium"
    return "medium"


def _risk_mitigation(risk: str) -> str:
    lowered = risk.lower()
    if any(term in lowered for term in ("security", "privacy", "credential", "compliance")):
        return "Require owner approval, access review, and rollback verification before pilot activation."
    if any(term in lowered for term in ("data", "migration", "sync")):
        return "Run reconciliation on sampled records and document exception ownership before expanding cohorts."
    if "integration" in lowered or "api" in lowered:
        return "Validate upstream and downstream contracts in a staging or pilot environment before rollout."
    return "Assign an explicit owner, mitigation check, and stop threshold before migration starts."


def _validation_warnings(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    evidence: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    checks = [
        ("specific_user", "Target user is missing; pilot cohort and training plan are inferred."),
        ("buyer", "Buyer or approving workflow owner is missing; rollout decision rights are inferred."),
        ("workflow_context", "Workflow context is missing; migration steps use a conservative generic workflow."),
        ("current_workaround", "Incumbent workflow is missing; rollback path needs validation before rollout."),
        ("mvp_scope", "MVP scope is missing; pilot acceptance checks use a generic first workflow."),
        ("validation_plan", "Validation plan is missing; go/no-go gates need an explicit review method."),
    ]
    for field, warning in checks:
        missing = not _string_list(design_brief.get(field)) or field in context["fallbacks_used"]
        if missing:
            warnings.append(
                {
                    "id": f"VW{len(warnings) + 1}",
                    "field": field,
                    "severity": "high" if field in {"current_workaround", "workflow_context"} else "medium",
                    "warning": warning,
                    "validation_needed": f"Confirm `{field}` before broad rollout.",
                }
            )
    if not source_idea_ids:
        warnings.append(
            {
                "id": f"VW{len(warnings) + 1}",
                "field": "source_idea_ids",
                "severity": "medium",
                "warning": "No source idea references are available for migration traceability.",
                "validation_needed": "Attach source idea IDs or document why this plan is brief-only.",
            }
        )
    if not evidence:
        warnings.append(
            {
                "id": f"VW{len(warnings) + 1}",
                "field": "evidence_references",
                "severity": "medium",
                "warning": "No evidence references support the migration plan.",
                "validation_needed": "Collect validation evidence before migrating production users.",
            }
        )
    readiness = float(design_brief.get("readiness_score") or 0.0)
    if readiness < 50:
        warnings.append(
            {
                "id": f"VW{len(warnings) + 1}",
                "field": "readiness_score",
                "severity": "medium",
                "warning": "Readiness score is low; keep migration to a reversible pilot.",
                "validation_needed": "Raise readiness with evidence, owner approval, and rollback rehearsal.",
            }
        )
    return warnings


def _evidence_references(
    design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for field in ("why_this_now", "synthesis_rationale", "validation_plan"):
        text = _first_text(design_brief.get(field))
        if text:
            refs.append(
                {
                    "id": f"design_brief.{field}",
                    "type": "brief_field",
                    "summary": text,
                    "source_idea_ids": list(design_brief.get("source_idea_ids") or []),
                }
            )
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        for signal_id in _string_list(idea.get("evidence_signals")):
            refs.append(
                {
                    "id": signal_id,
                    "type": "evidence_signal",
                    "summary": _first_text(idea.get("one_liner"), idea.get("problem"), idea["id"]),
                    "source_idea_ids": [idea["id"]],
                }
            )
        for insight_id in _string_list(idea.get("inspiring_insights")):
            refs.append(
                {
                    "id": insight_id,
                    "type": "inspiring_insight",
                    "summary": _first_text(idea.get("value_proposition"), idea.get("solution"), idea["id"]),
                    "source_idea_ids": [idea["id"]],
                }
            )
    return refs


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    ideas: list[dict[str, Any]] = []
    seen: set[str] = set()
    sources = list(design_brief.get("sources", []))
    if not sources:
        lead_id = design_brief.get("lead_idea_id")
        if lead_id:
            sources.append({"idea_id": lead_id, "role": "lead", "rank": 0})
        for rank, idea_id in enumerate(design_brief.get("source_idea_ids", []), start=1):
            if idea_id != lead_id:
                sources.append({"idea_id": idea_id, "role": "source", "rank": rank})

    for source in sources:
        idea_id = str(source["idea_id"])
        if idea_id in seen:
            continue
        seen.add(idea_id)
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            ideas.append(
                {
                    "id": idea_id,
                    "role": source.get("role", "source"),
                    "rank": source.get("rank", 0),
                    "missing": True,
                }
            )
            continue
        data = unit.model_dump(mode="json")
        data["role"] = source.get("role") or (
            "lead" if idea_id == design_brief.get("lead_idea_id") else "source"
        )
        data["rank"] = source.get("rank", 0 if data["role"] == "lead" else None)
        ideas.append(data)
    return ideas


def _source_ids_for_text(
    text: str, source_ideas: list[dict[str, Any]], fallback_ids: list[str]
) -> list[str]:
    source_ids: list[str] = []
    normalized = text.lower()
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        idea_text = " ".join(
            _string_list(
                [
                    idea.get("problem"),
                    idea.get("solution"),
                    idea.get("value_proposition"),
                    idea.get("workflow_context"),
                    idea.get("domain_risks"),
                ]
            )
        ).lower()
        if normalized and normalized in idea_text:
            source_ids.append(idea["id"])
    return source_ids or fallback_ids


def _field_values(items: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for item in items:
        if item.get("missing"):
            continue
        values.extend(_string_list(item.get(field)))
    return _dedupe_strings(values)


def _first_with_label(
    fallbacks: list[str], field: str, *candidates: tuple[Any, str]
) -> str:
    for value, label in candidates:
        text = _first_text(value)
        if text:
            if label == "explicit_fallback":
                fallbacks.append(field)
            return text
    return ""


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            text = _first_text(*value)
        else:
            text = _compact(value)
        if text:
            return text
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, set):
        return [_compact(item) for item in sorted(value, key=str) if _compact(item)]
    if isinstance(value, list | tuple | set):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(_compact(value) for value in values if _compact(value)))


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, set):
        value = sorted(value, key=str)
    if isinstance(value, (list, tuple)):
        return "; ".join(_csv_text(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
