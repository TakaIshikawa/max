"""Deterministic onboarding checklist export for persisted design briefs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.onboarding_checklist.v1"


def build_design_brief_onboarding_checklist(
    store: Store,
    brief_id: str,
) -> dict[str, Any] | None:
    """Build a customer onboarding checklist from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _onboarding_context(design_brief, source_ideas)
    setup_tasks = _setup_tasks(design_brief, source_ideas, source_idea_ids, context)
    data_access_requirements = _data_access_requirements(
        design_brief,
        source_ideas,
        source_idea_ids,
        context,
    )
    kickoff_agenda = _kickoff_agenda(design_brief, source_idea_ids, context)
    activation_milestones = _activation_milestones(design_brief, source_idea_ids, context)
    owner_roles = _owner_roles(context, source_idea_ids)
    evidence_references = _evidence_references(source_ideas, source_idea_ids)

    checklist_items = [
        *setup_tasks,
        *data_access_requirements,
        *kickoff_agenda,
        *activation_milestones,
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.onboarding_checklist",
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
            "buyer": context["buyer"],
            "specific_user": context["specific_user"],
            "workflow_context": context["workflow_context"],
        },
        "summary": {
            "onboarding_gate": _onboarding_gate(design_brief, context),
            "setup_task_count": len(setup_tasks),
            "data_access_requirement_count": len(data_access_requirements),
            "kickoff_agenda_count": len(kickoff_agenda),
            "activation_milestone_count": len(activation_milestones),
            "owner_role_count": len(owner_roles),
            "evidence_reference_count": len(evidence_references),
            "fallbacks_used": context["fallbacks_used"],
            "source_idea_count": len(source_idea_ids),
        },
        "onboarding_context": context,
        "setup_tasks": setup_tasks,
        "data_access_requirements": data_access_requirements,
        "kickoff_agenda": kickoff_agenda,
        "activation_milestones": activation_milestones,
        "owner_roles": owner_roles,
        "evidence_references": evidence_references,
        "checklist_items": checklist_items,
        "source_ideas": source_ideas,
    }


def render_design_brief_onboarding_checklist(
    report: dict[str, Any],
    fmt: str = "markdown",
) -> str:
    """Render an onboarding checklist as Markdown or deterministic JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported onboarding checklist format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Onboarding Checklist: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Buyer: {brief['buyer']}",
        f"User: {brief['specific_user']}",
        f"Workflow: {brief['workflow_context']}",
        f"Onboarding gate: {summary['onboarding_gate']}",
        f"Source ideas: {_inline_ids(brief.get('source_idea_ids') or [])}",
        "",
        "## Setup Tasks",
        "",
    ]
    for task in report["setup_tasks"]:
        lines.extend(_render_item(task))

    lines.extend(["## Data / Access Requirements", ""])
    for requirement in report["data_access_requirements"]:
        lines.extend(_render_item(requirement))

    lines.extend(["## Kickoff Agenda", ""])
    for agenda_item in report["kickoff_agenda"]:
        lines.extend(
            [
                f"### {agenda_item['id']}: {agenda_item['topic']}",
                "",
                f"- Owner role: {agenda_item['owner_role']}",
                f"- Goal: {agenda_item['goal']}",
                f"- Evidence to capture: {agenda_item['evidence_to_capture']}",
                f"- Source ideas: {_inline_ids(agenda_item['source_idea_ids'])}",
                "",
            ]
        )

    lines.extend(["## Activation Milestones", ""])
    for milestone in report["activation_milestones"]:
        lines.extend(
            [
                f"### {milestone['id']}: {milestone['name']}",
                "",
                f"- Owner role: {milestone['owner_role']}",
                f"- Target: {milestone['target']}",
                f"- Activation signal: {milestone['activation_signal']}",
                f"- Evidence to capture: {milestone['evidence_to_capture']}",
                f"- Source ideas: {_inline_ids(milestone['source_idea_ids'])}",
                "",
            ]
        )

    lines.extend(["## Owner Roles", ""])
    for role in report["owner_roles"]:
        lines.extend(
            [
                f"- **{role['role']}**: {role['responsibility']}",
                f"  Handoff evidence: {role['handoff_evidence']}",
            ]
        )

    lines.extend(["", "## Evidence References", ""])
    if report["evidence_references"]:
        for evidence in report["evidence_references"]:
            lines.append(
                f"- **{evidence['id']}** ({evidence['type']}): {evidence['label']} "
                f"[source ideas: {_inline_ids(evidence['source_idea_ids'])}]"
            )
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def onboarding_checklist_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    extension = "json" if fmt == "json" else "md"
    return (
        f"{_filename_part(str(design_brief['id']))}-"
        f"{_filename_part(str(design_brief['title']))}-onboarding-checklist.{extension}"
    )


def _onboarding_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> dict[str, Any]:
    fallbacks: list[str] = []
    title = str(design_brief["title"])
    buyer = _first_with_fallback(
        fallbacks,
        "buyer",
        design_brief.get("buyer"),
        _field_values(source_ideas, "buyer"),
        fallback="pilot sponsor",
    )
    specific_user = _first_with_fallback(
        fallbacks,
        "specific_user",
        design_brief.get("specific_user"),
        _field_values(source_ideas, "specific_user"),
        _field_values(source_ideas, "target_users"),
        fallback=f"{title} user",
    )
    workflow = _first_with_fallback(
        fallbacks,
        "workflow_context",
        design_brief.get("workflow_context"),
        _field_values(source_ideas, "workflow_context"),
        fallback=f"{title} pilot workflow",
    )
    scope_items = _string_list(design_brief.get("mvp_scope"))
    if not scope_items:
        fallbacks.append("mvp_scope")
    first_milestones = _string_list(design_brief.get("first_milestones"))
    if not first_milestones:
        fallbacks.append("first_milestones")
    validation_plan = _first_with_fallback(
        fallbacks,
        "validation_plan",
        design_brief.get("validation_plan"),
        _field_values(source_ideas, "validation_plan"),
        fallback=f"Validate first customer activation for {workflow}.",
    )
    value_proposition = _first_text(
        design_brief.get("merged_product_concept"),
        _field_values(source_ideas, "value_proposition"),
        f"Help {specific_user} complete {workflow}.",
    )
    risks = _dedupe([*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")])
    current_workaround = _first_text(
        _field_values(source_ideas, "current_workaround"),
        "the current manual workflow",
    )
    return {
        "buyer": buyer,
        "specific_user": specific_user,
        "workflow_context": workflow,
        "primary_scope": scope_items[0] if scope_items else f"first usable {title} workflow",
        "mvp_scope": scope_items,
        "first_milestones": first_milestones,
        "validation_plan": validation_plan,
        "value_proposition": value_proposition,
        "risks": risks,
        "primary_risk": risks[0] if risks else "No explicit onboarding risk captured.",
        "current_workaround": current_workaround,
        "fallbacks_used": fallbacks,
    }


def _setup_tasks(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    source_idea_ids: list[str],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        _item(
            item_id="DBOC1",
            task=f"Confirm pilot sponsor and onboarding owner for {context['buyer']}.",
            owner_role="Customer success owner",
            rationale=f"Onboarding needs one accountable buyer contact for {context['workflow_context']}.",
            completion_evidence="Named sponsor, day-to-day owner, and escalation contact are recorded.",
            source_fields=["buyer", "workflow_context"],
            source_idea_ids=_source_ids_for_fields(source_ideas, ("buyer", "workflow_context"), source_idea_ids),
        ),
        _item(
            item_id="DBOC2",
            task=f"Translate MVP scope into a first-session setup plan: {context['primary_scope']}.",
            owner_role="Product lead",
            rationale="; ".join(context["mvp_scope"]) or context["value_proposition"],
            completion_evidence="Customer-facing setup plan lists in-scope paths, non-goals, and prerequisites.",
            source_fields=["mvp_scope", "merged_product_concept"],
            source_idea_ids=source_idea_ids,
        ),
        _item(
            item_id="DBOC3",
            task="Prepare support and escalation path before enabling pilot users.",
            owner_role="Support owner",
            rationale=context["primary_risk"],
            completion_evidence="Support channel, escalation owner, and risk handling notes are visible to the team.",
            source_fields=["risks", "domain_risks"],
            source_idea_ids=_source_ids_for_fields(source_ideas, ("domain_risks",), source_idea_ids),
        ),
    ]


def _data_access_requirements(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    source_idea_ids: list[str],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    stack = _first_text(design_brief.get("tech_approach"), _joined_fields(source_ideas, ("tech_approach", "suggested_stack")))
    return [
        _item(
            item_id="DBOC4",
            task=f"List data, account, and permission prerequisites for {context['workflow_context']}.",
            owner_role="Implementation owner",
            rationale=stack or "Technical prerequisites are not explicit in the brief lineage.",
            completion_evidence="Access checklist names systems, credentials, data boundaries, and approval owner.",
            source_fields=["tech_approach", "suggested_stack", "workflow_context"],
            source_idea_ids=_source_ids_for_fields(
                source_ideas,
                ("tech_approach", "suggested_stack", "workflow_context"),
                source_idea_ids,
            ),
        ),
        _item(
            item_id="DBOC5",
            task="Capture baseline inputs from the current workaround before first use.",
            owner_role="Research lead",
            rationale=f"Current workaround: {context['current_workaround']}.",
            completion_evidence="Baseline includes current process, time or quality measure, and sample artifacts.",
            source_fields=["current_workaround", "validation_plan"],
            source_idea_ids=_source_ids_for_fields(
                source_ideas,
                ("current_workaround", "validation_plan"),
                source_idea_ids,
            ),
        ),
    ]


def _kickoff_agenda(
    design_brief: dict[str, Any],
    source_idea_ids: list[str],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "id": "KO1",
            "topic": "Pilot goal and success definition",
            "owner_role": "Product lead",
            "goal": context["value_proposition"],
            "evidence_to_capture": context["validation_plan"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "KO2",
            "topic": "Workflow walkthrough and setup prerequisites",
            "owner_role": "Implementation owner",
            "goal": f"Confirm how {context['specific_user']} will run {context['workflow_context']}.",
            "evidence_to_capture": "Confirmed workflow trigger, inputs, outputs, and missing access.",
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "KO3",
            "topic": "Scope, support, and escalation agreement",
            "owner_role": "Customer success owner",
            "goal": f"Set expectations for {design_brief['title']} pilot usage and support.",
            "evidence_to_capture": "Accepted MVP scope, support channel, escalation route, and next touchpoint.",
            "source_idea_ids": source_idea_ids,
        },
    ]


def _activation_milestones(
    design_brief: dict[str, Any],
    source_idea_ids: list[str],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    milestones = context["first_milestones"] or [
        f"Enable first {context['specific_user']}",
        f"Complete first {context['workflow_context']} run",
        "Review validation evidence with pilot sponsor",
    ]
    rendered: list[dict[str, Any]] = []
    for index, milestone in enumerate(milestones[:4], start=1):
        rendered.append(
            {
                "id": f"AM{index}",
                "name": milestone,
                "owner_role": _milestone_owner(index),
                "target": _milestone_target(index),
                "activation_signal": _activation_signal(index, context),
                "evidence_to_capture": _milestone_evidence(index, context),
                "source_idea_ids": source_idea_ids,
            }
        )
    return rendered


def _owner_roles(context: dict[str, Any], source_idea_ids: list[str]) -> list[dict[str, Any]]:
    roles = [
        (
            "Customer success owner",
            f"Coordinate onboarding with {context['buyer']} and keep pilot commitments current.",
            "Sponsor, owner, timeline, and communication channel are recorded.",
        ),
        (
            "Implementation owner",
            f"Prepare access and setup for {context['workflow_context']}.",
            "Prerequisites, setup status, blockers, and access decisions are recorded.",
        ),
        (
            "Product lead",
            "Own scope decisions, activation milestones, and pilot approval boundaries.",
            "MVP scope, milestone status, and scope changes are documented.",
        ),
        (
            "Research lead",
            "Capture baseline, activation, and validation evidence after pilot approval.",
            "Evidence log links baseline notes, activation signals, and validation outcomes.",
        ),
    ]
    return [
        {
            "id": f"OR{index}",
            "role": role,
            "responsibility": responsibility,
            "handoff_evidence": evidence,
            "source_idea_ids": source_idea_ids,
        }
        for index, (role, responsibility, evidence) in enumerate(roles, start=1)
    ]


def _evidence_references(
    source_ideas: list[dict[str, Any]],
    fallback_source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        for signal_id in _string_list(idea.get("evidence_signals")):
            key = ("signal", signal_id)
            if key in seen:
                continue
            seen.add(key)
            references.append(
                {
                    "id": signal_id,
                    "type": "signal",
                    "label": signal_id,
                    "source_idea_ids": [idea["id"]],
                }
            )
        for insight in _string_list(idea.get("inspiring_insights")):
            key = ("insight", insight)
            if key in seen:
                continue
            seen.add(key)
            references.append(
                {
                    "id": _filename_part(insight).lower(),
                    "type": "insight",
                    "label": insight,
                    "source_idea_ids": [idea["id"]],
                }
            )
    if references:
        return references
    return [
        {
            "id": "design-brief-lineage",
            "type": "lineage",
            "label": "Persisted design brief and source idea lineage.",
            "source_idea_ids": fallback_source_idea_ids,
        }
    ]


def _render_item(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item['id']}: {item['task']}",
        "",
        f"- Owner role: {item['owner_role']}",
        f"- Rationale: {item['rationale']}",
        f"- Source fields: {', '.join(item['source_fields'])}",
        f"- Completion evidence: {item['completion_evidence']}",
        f"- Status: {item['status']}",
        f"- Source ideas: {_inline_ids(item['source_idea_ids'])}",
        "",
    ]


def _item(
    *,
    item_id: str,
    task: str,
    owner_role: str,
    rationale: str,
    source_fields: list[str],
    completion_evidence: str,
    source_idea_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "status": "pending",
        "task": task,
        "owner_role": owner_role,
        "rationale": _compact(rationale),
        "source_fields": source_fields,
        "completion_evidence": completion_evidence,
        "source_idea_ids": list(dict.fromkeys(source_idea_ids)),
    }


def _onboarding_gate(design_brief: dict[str, Any], context: dict[str, Any]) -> str:
    status = design_brief.get("design_status")
    readiness = float(design_brief.get("readiness_score") or 0.0)
    if "validation_plan" in context["fallbacks_used"] or "mvp_scope" in context["fallbacks_used"]:
        return "needs_onboarding_inputs"
    if status in {"approved", "published"} and readiness >= 70:
        return "ready_for_customer_onboarding"
    if status in {"approved", "published"}:
        return "approved_needs_onboarding_readiness"
    return "needs_pilot_approval"


def _milestone_owner(index: int) -> str:
    return {
        1: "Implementation owner",
        2: "Customer success owner",
        3: "Research lead",
    }.get(index, "Product lead")


def _milestone_target(index: int) -> str:
    return {
        1: "Before kickoff or during the first setup session.",
        2: "Within the first active pilot workflow.",
        3: "Before the first pilot review.",
    }.get(index, "Before pilot expansion.")


def _activation_signal(index: int, context: dict[str, Any]) -> str:
    if index == 1:
        return f"{context['specific_user']} has the access and setup needed to start."
    if index == 2:
        return f"Customer completes a real {context['workflow_context']} attempt."
    if index == 3:
        return "Pilot sponsor can compare baseline and first-use outcome."
    return "Product lead records continue, revise, or stop decision."


def _milestone_evidence(index: int, context: dict[str, Any]) -> str:
    if index == 1:
        return "Setup completion note with unresolved blockers."
    if index == 2:
        return "First-use outcome, issue list, and customer quote or observation."
    if index == 3:
        return context["validation_plan"]
    return "Decision log entry with owner and next action."


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


def _source_ids_for_fields(
    source_ideas: list[dict[str, Any]],
    fields: tuple[str, ...],
    fallback: list[str],
) -> list[str]:
    ids = [
        idea["id"]
        for idea in source_ideas
        if not idea.get("missing") and any(_has_value(idea.get(field)) for field in fields)
    ]
    return list(dict.fromkeys(ids)) or fallback


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        values.extend(_string_list(idea.get(field)))
    return _dedupe(values)


def _joined_fields(source_ideas: list[dict[str, Any]], fields: tuple[str, ...]) -> str:
    values: list[str] = []
    for field in fields:
        values.extend(_field_values(source_ideas, field))
    return "; ".join(_dedupe(values))


def _first_with_fallback(
    fallbacks: list[str],
    field: str,
    *values: Any,
    fallback: str,
) -> str:
    text = _first_text(*values)
    if text:
        return text
    fallbacks.append(field)
    return fallback


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            text = _compact("; ".join(value))
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
    if isinstance(value, dict):
        return [_compact(f"{key}: {item}") for key, item in value.items() if _compact(key)]
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(_compact(value) for value in values if _compact(value)))


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "none"


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    return cleaned.strip("-_") or "design-brief"
