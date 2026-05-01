"""Deterministic implementation work breakdowns for persisted design briefs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.work_breakdown"
SCHEMA_VERSION = "max.design_brief.work_breakdown.v1"

_REQUIRED_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("specific_user", "medium", "Implementation tasks need a named primary actor."),
    ("buyer", "medium", "Owner review and acceptance checks need a buyer or accountable approver."),
    ("workflow_context", "high", "Task sequencing needs the workflow where the first release is used."),
    ("merged_product_concept", "high", "Epics need a concrete product concept to avoid speculative work."),
    ("mvp_scope", "high", "Task boundaries need an explicit MVP scope."),
    ("first_milestones", "medium", "Sequencing needs first milestone expectations."),
    ("validation_plan", "high", "Acceptance checks need owner-approved validation criteria."),
    ("risks", "medium", "Sequencing risks need known failure modes."),
    ("source_idea_ids", "medium", "Work items need source traceability."),
)


def build_design_brief_work_breakdown(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build implementation-ready epics, tasks, checks, and risks from a design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _work_context(design_brief, source_ideas)
    gaps = _gaps(design_brief, source_ideas, context, source_idea_ids)
    owners = _owners(context)
    acceptance_checks = _acceptance_checks(context, source_idea_ids, bool(gaps))
    epics = _epics(context, source_idea_ids, bool(gaps))
    tasks = _tasks(context, epics, acceptance_checks, source_idea_ids, bool(gaps))
    dependencies = _dependencies(tasks, context, bool(gaps))
    sequencing_risks = _sequencing_risks(context, gaps, source_idea_ids)
    next_actions = _next_actions(context, gaps)

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
            "epic_count": len(epics),
            "task_count": len(tasks),
            "dependency_count": len(dependencies),
            "owner_count": len(owners),
            "acceptance_check_count": len(acceptance_checks),
            "sequencing_risk_count": len(sequencing_risks),
            "gap_count": len(gaps),
            "next_action_count": len(next_actions),
            "fallbacks_used": context["fallbacks_used"],
            "implementation_gate": "resolve_gaps_first" if gaps else "ready_for_execution_planning",
        },
        "work_context": context,
        "epics": epics,
        "tasks": tasks,
        "dependencies": dependencies,
        "owners": owners,
        "acceptance_checks": acceptance_checks,
        "sequencing_risks": sequencing_risks,
        "gaps": gaps,
        "next_actions": next_actions,
        "source_ideas": source_ideas,
    }


def render_design_brief_work_breakdown(report: dict[str, Any], fmt: str = "markdown") -> str:
    """Render a design brief work breakdown as Markdown or deterministic JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported work breakdown format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Work Breakdown: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Implementation gate: {summary['implementation_gate']}",
        f"Source ideas: {_inline_list(brief.get('source_idea_ids') or [])}",
        "",
        "## Context",
        "",
        f"- Product concept: {report['work_context']['product_concept']}",
        f"- Primary user: {report['work_context']['specific_user']}",
        f"- Buyer: {report['work_context']['buyer']}",
        f"- Workflow: {report['work_context']['workflow_context']}",
        f"- Fallbacks used: {_inline_list(summary['fallbacks_used'])}",
        "",
        "## Epics",
        "",
    ]

    tasks_by_epic: dict[str, list[dict[str, Any]]] = {}
    for task in report["tasks"]:
        tasks_by_epic.setdefault(task["epic_id"], []).append(task)

    for epic in report["epics"]:
        lines.extend(
            [
                f"### {epic['id']}: {epic['title']}",
                "",
                f"- Owner: {epic['owner']}",
                f"- Objective: {epic['objective']}",
                f"- Exit criteria: {epic['exit_criteria']}",
                "- Tasks:",
            ]
        )
        for task in tasks_by_epic.get(epic["id"], []):
            lines.append(
                f"  - **{task['id']}** {task['title']} ({task['owner']}; depends on: {_inline_list(task['depends_on'])})"
            )
        lines.append("")

    lines.extend(["## Dependencies", ""])
    for dependency in report["dependencies"]:
        lines.append(
            f"- **{dependency['id']}** {dependency['from_task_id']} -> {dependency['to_task_id']}: {dependency['rationale']}"
        )

    lines.extend(["", "## Owners", ""])
    for owner in report["owners"]:
        lines.append(f"- **{owner['role']}**: {owner['responsibility']} Handoff: {owner['handoff']}")

    lines.extend(["", "## Acceptance Checks", ""])
    for check in report["acceptance_checks"]:
        lines.append(f"- **{check['id']} {check['name']}** ({check['owner']}): {check['criteria']}")

    lines.extend(["", "## Sequencing Risks", ""])
    for risk in report["sequencing_risks"]:
        lines.append(f"- **{risk['id']} {risk['risk']}** ({risk['severity']}): {risk['mitigation']}")

    lines.extend(["", "## Gaps", ""])
    if report["gaps"]:
        for gap in report["gaps"]:
            lines.append(f"- **{gap['id']} {gap['field']}** ({gap['severity']}): {gap['gap']}")
    else:
        lines.append("- None")

    lines.extend(["", "## Next Actions", ""])
    for action in report["next_actions"]:
        lines.append(f"- **{action['id']}** ({action['owner']}): {action['action']}")

    return "\n".join(lines).rstrip() + "\n"


def work_breakdown_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    """Return a stable filename for a work breakdown export."""
    extension = "json" if fmt == "json" else "md"
    return (
        f"{_filename_part(str(design_brief['id']))}-"
        f"{_filename_part(str(design_brief['title']))}-work-breakdown.{extension}"
    )


def _work_context(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> dict[str, Any]:
    fallbacks: list[str] = []
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    title = _first_text(design_brief.get("title"), "Untitled design brief")
    specific_user = _first_with_label(
        fallbacks,
        "specific_user",
        (design_brief.get("specific_user"), "design_brief.specific_user"),
        (lead_idea and lead_idea.get("specific_user"), "lead_idea.specific_user"),
        (_field_values(source_ideas, "specific_user"), "source_ideas.specific_user"),
        (f"{title} primary user", "explicit_fallback"),
    )
    buyer = _first_with_label(
        fallbacks,
        "buyer",
        (design_brief.get("buyer"), "design_brief.buyer"),
        (lead_idea and lead_idea.get("buyer"), "lead_idea.buyer"),
        (_field_values(source_ideas, "buyer"), "source_ideas.buyer"),
        ("product owner", "explicit_fallback"),
    )
    workflow = _first_with_label(
        fallbacks,
        "workflow_context",
        (design_brief.get("workflow_context"), "design_brief.workflow_context"),
        (lead_idea and lead_idea.get("workflow_context"), "lead_idea.workflow_context"),
        (_field_values(source_ideas, "workflow_context"), "source_ideas.workflow_context"),
        (f"{title} workflow", "explicit_fallback"),
    )
    product_concept = _first_with_label(
        fallbacks,
        "merged_product_concept",
        (design_brief.get("merged_product_concept"), "design_brief.merged_product_concept"),
        (lead_idea and lead_idea.get("solution"), "lead_idea.solution"),
        (_field_values(source_ideas, "solution"), "source_ideas.solution"),
        (f"{title} implementation", "explicit_fallback"),
    )
    mvp_scope = _string_list(design_brief.get("mvp_scope"))
    if not mvp_scope:
        fallbacks.append("mvp_scope")
        mvp_scope = [f"first usable {workflow} workflow"]
    first_milestones = _string_list(design_brief.get("first_milestones"))
    if not first_milestones:
        fallbacks.append("first_milestones")
        first_milestones = ["confirm implementation boundary", "ship owner-reviewed handoff"]
    validation_plan = _first_with_label(
        fallbacks,
        "validation_plan",
        (design_brief.get("validation_plan"), "design_brief.validation_plan"),
        (lead_idea and lead_idea.get("validation_plan"), "lead_idea.validation_plan"),
        (_field_values(source_ideas, "validation_plan"), "source_ideas.validation_plan"),
        ("Record product, engineering, and QA acceptance before implementation starts.", "explicit_fallback"),
    )
    risks = _dedupe_strings(
        [
            *_string_list(design_brief.get("risks")),
            *_field_values(source_ideas, "domain_risks"),
        ]
    )
    if not risks:
        fallbacks.append("risks")
        risks = ["Unknown sequencing or quality risk; keep implementation gated by owner review."]

    return {
        "title": title,
        "domain": _first_text(design_brief.get("domain"), "general"),
        "theme": _first_text(design_brief.get("theme")),
        "readiness_score": float(design_brief.get("readiness_score") or 0.0),
        "specific_user": specific_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "product_concept": product_concept,
        "primary_scope": mvp_scope[0],
        "secondary_scope": mvp_scope[1] if len(mvp_scope) > 1 else first_milestones[0],
        "mvp_scope": mvp_scope,
        "first_milestones": first_milestones,
        "validation_plan": validation_plan,
        "risks": risks[:5],
        "fallbacks_used": _dedupe_strings(fallbacks),
    }


def _epics(
    context: dict[str, Any],
    source_idea_ids: list[str],
    has_gaps: bool,
) -> list[dict[str, Any]]:
    gap_clause = " Gap disposition must be recorded before scope expands." if has_gaps else ""
    return [
        {
            "id": "WBE1",
            "title": "Execution Foundation",
            "owner": "Product owner",
            "objective": f"Translate {context['product_concept']} into a buildable contract for {context['specific_user']}.",
            "exit_criteria": f"MVP boundary, source assumptions, and owner decisions are explicit.{gap_clause}",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "WBE2",
            "title": "Core Workflow Build",
            "owner": "Implementation engineer",
            "objective": f"Implement the first {context['workflow_context']} path for {context['primary_scope']}.",
            "exit_criteria": "Core workflow runs against representative fixtures with deterministic behavior.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "WBE3",
            "title": "Validation and Quality Gates",
            "owner": "QA engineer",
            "objective": f"Prove the implementation satisfies {context['validation_plan']}",
            "exit_criteria": "Unit, integration, acceptance, and regression checks are passing or dispositioned.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "WBE4",
            "title": "Launch Handoff",
            "owner": "Release owner",
            "objective": f"Prepare {context['buyer']} to approve rollout and recovery decisions.",
            "exit_criteria": "Launch notes, rollback criteria, and post-launch evidence capture are owner-approved.",
            "source_idea_ids": source_idea_ids,
        },
    ]


def _tasks(
    context: dict[str, Any],
    epics: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    source_idea_ids: list[str],
    has_gaps: bool,
) -> list[dict[str, Any]]:
    check_ids = [check["id"] for check in checks]
    tasks = [
        _task("WBT1", epics[0], "Resolve build contract", "Confirm MVP scope, non-goals, source assumptions, and open gaps.", "Product owner", [], check_ids[:2], ["mvp_scope", "merged_product_concept", "source_idea_ids"], source_idea_ids),
        _task("WBT2", epics[0], "Define implementation slices", f"Break {context['primary_scope']} into reviewable engineering slices.", "Implementation engineer", ["WBT1"], check_ids[:2], ["first_milestones", "workflow_context"], source_idea_ids),
        _task("WBT3", epics[1], "Build primary workflow", f"Implement the {context['workflow_context']} happy path for {context['specific_user']}.", "Implementation engineer", ["WBT2"], check_ids[1:4], ["specific_user", "workflow_context", "mvp_scope"], source_idea_ids),
        _task("WBT4", epics[1], "Build operational edge handling", f"Handle empty, invalid, duplicated, and deferred states for {context['secondary_scope']}.", "Implementation engineer", ["WBT3"], check_ids[2:4], ["risks", "first_milestones"], source_idea_ids),
        _task("WBT5", epics[2], "Automate regression coverage", "Add deterministic tests for structured output, rendering, and repeated generation.", "QA engineer", ["WBT3", "WBT4"], check_ids[2:5], ["validation_plan", "risks"], source_idea_ids),
        _task("WBT6", epics[2], "Run owner acceptance review", f"Validate the build against: {context['validation_plan']}", "Product owner", ["WBT5"], check_ids[3:6], ["validation_plan", "buyer"], source_idea_ids),
        _task("WBT7", epics[3], "Prepare launch handoff", f"Document release notes, support expectations, and recovery triggers for {context['buyer']}.", "Release owner", ["WBT6"], check_ids[4:6], ["buyer", "risks"], source_idea_ids),
        _task("WBT8", epics[3], "Close evidence loop", "Record acceptance evidence, unresolved decisions, and the next build increment.", "Product owner", ["WBT7"], check_ids[5:], ["validation_plan", "first_milestones"], source_idea_ids),
    ]
    if has_gaps:
        tasks[0]["status"] = "blocked_until_gap_review"
        for task in tasks[1:]:
            task["status"] = "planned_after_gap_review"
    return tasks


def _task(
    id: str,
    epic: dict[str, Any],
    title: str,
    description: str,
    owner: str,
    depends_on: list[str],
    acceptance_check_ids: list[str],
    source_fields: list[str],
    source_idea_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": id,
        "epic_id": epic["id"],
        "title": title,
        "description": description,
        "owner": owner,
        "depends_on": depends_on,
        "acceptance_check_ids": acceptance_check_ids,
        "source_fields": source_fields,
        "source_idea_ids": source_idea_ids,
        "status": "planned",
    }


def _dependencies(
    tasks: list[dict[str, Any]],
    context: dict[str, Any],
    has_gaps: bool,
) -> list[dict[str, Any]]:
    dependencies: list[dict[str, Any]] = []
    task_by_id = {task["id"]: task for task in tasks}
    for task in tasks:
        for prerequisite in task["depends_on"]:
            dependencies.append(
                {
                    "id": f"WBD{len(dependencies) + 1}",
                    "from_task_id": prerequisite,
                    "to_task_id": task["id"],
                    "type": "finish_to_start",
                    "rationale": f"{task['title']} depends on {task_by_id[prerequisite]['title']} before changing {context['workflow_context']}.",
                    "risk_if_skipped": "Implementation may proceed without agreed scope, validation evidence, or owner review.",
                }
            )
    if has_gaps:
        dependencies.insert(
            0,
            {
                "id": "WBD0",
                "from_task_id": "gaps",
                "to_task_id": "WBT1",
                "type": "gate",
                "rationale": "Explicit gaps must be dispositioned before the work contract is treated as executable.",
                "risk_if_skipped": "Sparse brief inputs could become unreviewed implementation commitments.",
            },
        )
    return dependencies


def _owners(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "role": "Product owner",
            "responsibility": f"Own scope, buyer review, and acceptance for {context['product_concept']}.",
            "handoff": "Approved scope, non-goals, validation decision, and next increment.",
        },
        {
            "role": "Implementation engineer",
            "responsibility": f"Build the deterministic {context['workflow_context']} workflow and edge handling.",
            "handoff": "Code, fixtures, technical notes, and unresolved engineering tradeoffs.",
        },
        {
            "role": "QA engineer",
            "responsibility": "Own automated and manual quality gates across sparse and rich inputs.",
            "handoff": "Passing checks, skipped checks with rationale, and regression risks.",
        },
        {
            "role": "Release owner",
            "responsibility": f"Coordinate rollout readiness, support expectations, and recovery for {context['buyer']}.",
            "handoff": "Launch checklist, rollback triggers, and evidence capture plan.",
        },
    ]


def _acceptance_checks(
    context: dict[str, Any],
    source_idea_ids: list[str],
    has_gaps: bool,
) -> list[dict[str, Any]]:
    gap_criterion = (
        "Every gap is assigned an owner, disposition, and build impact before downstream tasks start."
        if has_gaps
        else "No blocking brief gaps remain for implementation handoff."
    )
    return [
        {
            "id": "WBAC1",
            "name": "Scope contract accepted",
            "owner": "Product owner",
            "criteria": f"MVP scope is limited to {context['primary_scope']} with explicit non-goals.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "WBAC2",
            "name": "Source traceability preserved",
            "owner": "Product owner",
            "criteria": "Tasks and acceptance checks retain source idea references or explain brief-only provenance.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "WBAC3",
            "name": "Core workflow verified",
            "owner": "Implementation engineer",
            "criteria": f"{context['specific_user']} can complete {context['workflow_context']} in representative fixtures.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "WBAC4",
            "name": "Risk paths covered",
            "owner": "QA engineer",
            "criteria": f"Top risks have tests or manual review: {_inline_list(context['risks'])}.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "WBAC5",
            "name": "Validation plan satisfied",
            "owner": "Product owner",
            "criteria": context["validation_plan"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "WBAC6",
            "name": "Gap disposition complete",
            "owner": "Release owner",
            "criteria": gap_criterion,
            "source_idea_ids": source_idea_ids,
        },
    ]


def _sequencing_risks(
    context: dict[str, Any],
    gaps: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    risks = [
        {
            "id": "WBSR1",
            "risk": "Scope expands before the build contract is accepted",
            "severity": "high" if gaps else "medium",
            "mitigation": "Keep WBT1 as the first gate and require explicit non-goals before build tasks start.",
            "related_task_ids": ["WBT1", "WBT2"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "WBSR2",
            "risk": "Validation happens after implementation choices harden",
            "severity": "high",
            "mitigation": "Attach WBAC5 to implementation and acceptance tasks before launch handoff.",
            "related_task_ids": ["WBT5", "WBT6"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "WBSR3",
            "risk": context["risks"][0],
            "severity": "medium",
            "mitigation": "Map the risk to regression checks, manual review, or an explicit defer decision.",
            "related_task_ids": ["WBT4", "WBT5", "WBT7"],
            "source_idea_ids": source_idea_ids,
        },
    ]
    if gaps:
        risks.append(
            {
                "id": "WBSR4",
                "risk": "Sparse brief data is converted into unreviewed implementation scope",
                "severity": "high",
                "mitigation": "Resolve or defer every gap before moving beyond WBT1.",
                "related_task_ids": ["WBT1"],
                "source_idea_ids": source_idea_ids,
            }
        )
    return risks


def _gaps(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    context: dict[str, Any],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for field, severity, reason in _REQUIRED_FIELDS:
        if field == "source_idea_ids":
            missing = not source_idea_ids
        elif field in {"mvp_scope", "first_milestones", "risks"}:
            missing = not _string_list(design_brief.get(field))
        else:
            missing = not _string_list(design_brief.get(field)) and not _field_values(source_ideas, field)
        if missing or field in context["fallbacks_used"]:
            gaps.append(
                {
                    "id": f"WBG{len(gaps) + 1}",
                    "field": field,
                    "severity": severity,
                    "gap": reason,
                    "needed_for_execution": f"Provide `{field}` or record an owner-approved defer decision.",
                    "source_idea_ids": source_idea_ids,
                }
            )
    missing_source_ids = [idea["id"] for idea in source_ideas if idea.get("missing")]
    for idea_id in missing_source_ids:
        gaps.append(
            {
                "id": f"WBG{len(gaps) + 1}",
                "field": "missing_source_idea",
                "severity": "medium",
                "gap": f"Source idea `{idea_id}` is referenced but not available in the store.",
                "needed_for_execution": "Restore the source idea or document why the brief can be executed without it.",
                "source_idea_ids": [idea_id],
            }
        )
    return gaps


def _next_actions(context: dict[str, Any], gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if gaps:
        actions.append(
            {
                "id": "WBNA1",
                "owner": "Product owner",
                "action": "Review and disposition every work breakdown gap before starting implementation slices.",
                "related_gap_ids": [gap["id"] for gap in gaps],
            }
        )
    actions.extend(
        [
            {
                "id": f"WBNA{len(actions) + 1}",
                "owner": "Implementation engineer",
                "action": f"Start WBT1 by converting {context['primary_scope']} into concrete build notes and non-goals.",
                "related_gap_ids": [],
            },
            {
                "id": f"WBNA{len(actions) + 2}",
                "owner": "QA engineer",
                "action": "Prepare regression fixtures for rich, sparse, duplicate, and missing-source brief inputs.",
                "related_gap_ids": [],
            },
            {
                "id": f"WBNA{len(actions) + 3}",
                "owner": "Release owner",
                "action": f"Define launch and rollback evidence {context['buyer']} must review before rollout.",
                "related_gap_ids": [],
            },
        ]
    )
    return actions


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


def _field_values(items: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for item in items:
        if item.get("missing"):
            continue
        values.extend(_string_list(item.get(field)))
    return _dedupe_strings(values)


def _first_with_label(
    fallbacks: list[str],
    field: str,
    *candidates: tuple[Any, str],
) -> str:
    for value, label in candidates:
        text = _first_text(value)
        if text:
            if label == "explicit_fallback":
                fallbacks.append(field)
            return text
    fallbacks.append(field)
    return ""


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
    return ""


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _inline_list(values: list[str]) -> str:
    return ", ".join(values) if values else "None"


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    parts = [part for part in cleaned.replace("_", "-").split("-") if part]
    return "-".join(parts) or "design-brief"
