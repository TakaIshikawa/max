"""Deterministic training plans for persisted design briefs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.training_plan"
SCHEMA_VERSION = "max.design_brief.training_plan.v1"


def build_design_brief_training_plan(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a customer and internal training plan from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _training_context(design_brief, source_ideas, lead_idea)
    learner_segments = _learner_segments(context, source_idea_ids)
    objectives = _learning_objectives(design_brief, context, source_idea_ids)
    outline = _session_outline(context, objectives, source_idea_ids)
    setup = _prerequisite_setup(design_brief, context, source_idea_ids)
    exercises = _hands_on_exercises(context, objectives, source_idea_ids)
    checks = _success_checks(design_brief, context, exercises, source_idea_ids)
    materials = _follow_up_materials(context, source_idea_ids)
    evidence = _evidence_references(design_brief, source_ideas)
    gaps = _gaps_to_resolve(design_brief, context, evidence)
    next_actions = _next_actions(gaps)

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
            "training_goal": f"Prepare customer and internal learners to use and support {design_brief['title']}.",
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "workflow_context": context["workflow_context"],
            "primary_scope": context["primary_scope"],
            "fallbacks_used": context["fallbacks_used"],
            "learner_segment_count": len(learner_segments),
            "learning_objective_count": len(objectives),
            "exercise_count": len(exercises),
            "success_check_count": len(checks),
            "gap_count": len(gaps),
        },
        "learner_segments": learner_segments,
        "learning_objectives": objectives,
        "session_outline": outline,
        "prerequisite_setup": setup,
        "hands_on_exercises": exercises,
        "success_checks": checks,
        "follow_up_materials": materials,
        "evidence_references": evidence,
        "gaps_to_resolve": gaps,
        "next_actions": next_actions,
        "source_ideas": source_ideas,
    }


def render_design_brief_training_plan(report: dict[str, Any], fmt: str = "json") -> str:
    """Render a training plan as JSON or Markdown."""
    if fmt == "json":
        return json.dumps(report, indent=2) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported training plan format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Training Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {', '.join(brief.get('source_idea_ids') or []) or 'design brief'}",
        "",
        "## Training Summary",
        "",
        f"- Goal: {summary['training_goal']}",
        f"- Target user: {summary['target_user']}",
        f"- Buyer: {summary['buyer']}",
        f"- Workflow: {summary['workflow_context']}",
        f"- Primary scope: {summary['primary_scope']}",
        f"- Fallbacks used: {', '.join(summary['fallbacks_used']) or 'none'}",
        "",
        "## Learner Segments",
        "",
    ]

    for segment in report["learner_segments"]:
        lines.extend(
            [
                f"### {segment['name']}",
                "",
                f"- Type: {segment['type']}",
                f"- Training need: {segment['training_need']}",
                f"- Expected outcome: {segment['expected_outcome']}",
                f"- Delivery mode: {segment['delivery_mode']}",
                "",
            ]
        )

    lines.extend(["## Learning Objectives", ""])
    for objective in report["learning_objectives"]:
        lines.extend(
            [
                f"- **{objective['id']}**: {objective['objective']}",
                f"  Measure: {objective['measure']}",
            ]
        )

    lines.extend(["", "## Session Outline", ""])
    for item in report["session_outline"]:
        lines.extend(
            [
                f"### {item['sequence']}. {item['title']}",
                "",
                f"- Duration: {item['duration']}",
                f"- Audience: {item['audience']}",
                f"- Purpose: {item['purpose']}",
                f"- Output: {item['output']}",
                "",
            ]
        )

    lines.extend(["## Prerequisite Setup", ""])
    for item in report["prerequisite_setup"]:
        lines.extend(
            [
                f"- **{item['id']} {item['name']}** ({item['owner']}): {item['instruction']}",
                f"  Ready when: {item['ready_when']}",
            ]
        )

    lines.extend(["", "## Hands-On Exercises", ""])
    for exercise in report["hands_on_exercises"]:
        lines.extend(
            [
                f"### {exercise['id']}: {exercise['title']}",
                "",
                f"- Learner segment: {exercise['learner_segment_id']}",
                f"- Scenario: {exercise['scenario']}",
                f"- Task: {exercise['task']}",
                f"- Debrief prompt: {exercise['debrief_prompt']}",
                "",
            ]
        )

    lines.extend(["## Success Checks", ""])
    for check in report["success_checks"]:
        lines.extend(
            [
                f"- **{check['id']}**: {check['check']}",
                f"  Passing signal: {check['passing_signal']}",
            ]
        )

    lines.extend(["", "## Follow-Up Materials", ""])
    for material in report["follow_up_materials"]:
        lines.extend(
            [
                f"- **{material['name']}** ({material['audience']}): {material['purpose']}",
                f"  Owner: {material['owner']}",
            ]
        )

    lines.extend(["", "## Evidence References", ""])
    if report["evidence_references"]:
        for item in report["evidence_references"]:
            lines.append(f"- **{item['id']}** ({item['type']}): {item['summary']}")
    else:
        lines.append("- None")

    lines.extend(["", "## Gaps To Resolve Before Training", ""])
    if report["gaps_to_resolve"]:
        for gap in report["gaps_to_resolve"]:
            lines.extend(
                [
                    f"- **{gap['id']} {gap['field']}**: {gap['gap']}",
                    f"  Next action: {gap['next_action']}",
                ]
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Next Actions", ""])
    if report["next_actions"]:
        for action in report["next_actions"]:
            lines.append(f"- **{action['id']}** ({action['owner']}): {action['action']}")
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def training_plan_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    """Return a stable filename for a training plan export."""
    extension = "json" if fmt == "json" else "md"
    brief_id = _filename_part(str(design_brief.get("id") or "design-brief"))
    title = _filename_part(str(design_brief.get("title") or "training-plan"))
    return f"{brief_id}-{title}-training-plan.{extension}"


def _training_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    lead_idea: dict[str, Any] | None,
) -> dict[str, Any]:
    fallbacks: list[str] = []
    title = str(design_brief["title"])
    buyer = _first_with_label(
        fallbacks,
        "buyer",
        (design_brief.get("buyer"), "design_brief.buyer"),
        (lead_idea and lead_idea.get("buyer"), "lead_idea.buyer"),
        (_field_values(source_ideas, "buyer"), "source_ideas.buyer"),
        ("training sponsor", "explicit_fallback"),
    )
    target_user = _first_with_label(
        fallbacks,
        "specific_user",
        (design_brief.get("specific_user"), "design_brief.specific_user"),
        (lead_idea and lead_idea.get("specific_user"), "lead_idea.specific_user"),
        (_field_values(source_ideas, "specific_user"), "source_ideas.specific_user"),
        (f"{title} user", "explicit_fallback"),
    )
    workflow = _first_with_label(
        fallbacks,
        "workflow_context",
        (design_brief.get("workflow_context"), "design_brief.workflow_context"),
        (lead_idea and lead_idea.get("workflow_context"), "lead_idea.workflow_context"),
        (_field_values(source_ideas, "workflow_context"), "source_ideas.workflow_context"),
        (f"{title} workflow", "explicit_fallback"),
    )
    scope = _string_list(design_brief.get("mvp_scope"))
    milestones = _string_list(design_brief.get("first_milestones"))
    validation_plan = _first_text(
        design_brief.get("validation_plan"),
        lead_idea and lead_idea.get("validation_plan"),
        "Validate that learners can complete the first workflow without facilitator help.",
    )
    value = _first_text(
        design_brief.get("merged_product_concept"),
        lead_idea and lead_idea.get("value_proposition"),
        lead_idea and lead_idea.get("solution"),
        f"Help {target_user} complete {workflow}.",
    )
    return {
        "title": title,
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "primary_scope": scope[0] if scope else f"first usable {title} workflow",
        "first_milestone": milestones[0] if milestones else "first trained cohort completes the workflow",
        "validation_plan": validation_plan,
        "value_proposition": value,
        "fallbacks_used": fallbacks,
    }


def _learner_segments(context: dict[str, Any], source_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": "customer_practitioners",
            "name": "Customer practitioners",
            "type": "customer",
            "training_need": f"Complete {context['primary_scope']} in {context['workflow_context']}.",
            "expected_outcome": "Can complete the trained workflow and explain when to use it.",
            "delivery_mode": "live workshop with recorded walkthrough",
            "source_idea_ids": source_ids,
        },
        {
            "id": "customer_sponsors",
            "name": "Customer sponsors",
            "type": "customer",
            "training_need": "Understand value, adoption signals, and escalation paths.",
            "expected_outcome": f"Can judge whether {context['first_milestone']} is achieved.",
            "delivery_mode": "briefing plus success-check rubric",
            "source_idea_ids": source_ids,
        },
        {
            "id": "internal_gtm_support",
            "name": "Internal GTM and support",
            "type": "internal",
            "training_need": "Handle positioning, qualification, objections, and support routing.",
            "expected_outcome": "Can coach customers and route unresolved issues to the product owner.",
            "delivery_mode": "enablement session with exercise review",
            "source_idea_ids": source_ids,
        },
        {
            "id": "internal_product_engineering",
            "name": "Internal product and engineering",
            "type": "internal",
            "training_need": "Observe learning friction and turn it into product or documentation follow-up.",
            "expected_outcome": "Can interpret training evidence and prioritize fixes.",
            "delivery_mode": "facilitator prep and post-session review",
            "source_idea_ids": source_ids,
        },
    ]


def _learning_objectives(
    design_brief: dict[str, Any], context: dict[str, Any], source_ids: list[str]
) -> list[dict[str, Any]]:
    risks = _string_list(design_brief.get("risks"))
    return [
        {
            "id": "LO1",
            "objective": f"Explain where {context['title']} fits in {context['workflow_context']}.",
            "measure": "Learner can name the workflow trigger, expected user, and handoff point.",
            "source_idea_ids": source_ids,
            "source_fields": ["specific_user", "workflow_context"],
        },
        {
            "id": "LO2",
            "objective": f"Complete {context['primary_scope']} using the trained path.",
            "measure": "Learner completes the exercise without unplanned facilitator intervention.",
            "source_idea_ids": source_ids,
            "source_fields": ["mvp_scope"],
        },
        {
            "id": "LO3",
            "objective": f"Connect the workflow to the value proposition: {context['value_proposition']}",
            "measure": "Learner can summarize the expected outcome in customer language.",
            "source_idea_ids": source_ids,
            "source_fields": ["merged_product_concept"],
        },
        {
            "id": "LO4",
            "objective": "Recognize training blockers, risks, and escalation criteria.",
            "measure": risks[0] if risks else "Learner can identify when to pause and escalate unresolved friction.",
            "source_idea_ids": source_ids,
            "source_fields": ["risks", "validation_plan"],
        },
    ]


def _session_outline(
    context: dict[str, Any], objectives: list[dict[str, Any]], source_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "id": "SO1",
            "sequence": 1,
            "title": "Workflow framing",
            "duration": "10 minutes",
            "audience": "all learners",
            "purpose": objectives[0]["objective"],
            "output": f"Shared understanding of {context['workflow_context']}.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "SO2",
            "sequence": 2,
            "title": "Facilitated walkthrough",
            "duration": "20 minutes",
            "audience": "customer practitioners and internal coaches",
            "purpose": objectives[1]["objective"],
            "output": "Annotated workflow run with common mistakes captured.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "SO3",
            "sequence": 3,
            "title": "Hands-on practice",
            "duration": "30 minutes",
            "audience": "segment-specific breakout groups",
            "purpose": "Practice the workflow, sponsor interpretation, and support coaching paths.",
            "output": "Completed exercises and open questions.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "SO4",
            "sequence": 4,
            "title": "Success check and follow-up",
            "duration": "15 minutes",
            "audience": "all learners",
            "purpose": context["validation_plan"],
            "output": "Pass/fail evidence, follow-up owners, and training gaps.",
            "source_idea_ids": source_ids,
        },
    ]


def _prerequisite_setup(
    design_brief: dict[str, Any], context: dict[str, Any], source_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "id": "PS1",
            "name": "Training cohort",
            "owner": "Customer success",
            "instruction": f"Invite {context['target_user']} learners and the {context['buyer']} sponsor.",
            "ready_when": "Each learner has a named role, session time, and attendance owner.",
            "source_idea_ids": source_ids,
            "source_fields": ["specific_user", "buyer"],
        },
        {
            "id": "PS2",
            "name": "Exercise environment",
            "owner": "Product engineering",
            "instruction": f"Prepare a safe workspace for {context['primary_scope']}.",
            "ready_when": "The facilitator can reset data and run the exercise from a clean state.",
            "source_idea_ids": source_ids,
            "source_fields": ["mvp_scope"],
        },
        {
            "id": "PS3",
            "name": "Validation rubric",
            "owner": "Product lead",
            "instruction": _first_text(
                design_brief.get("validation_plan"),
                "Define pass/fail criteria before the first training session.",
            ),
            "ready_when": "Success checks are visible to facilitators before learners start exercises.",
            "source_idea_ids": source_ids,
            "source_fields": ["validation_plan"],
        },
    ]


def _hands_on_exercises(
    context: dict[str, Any], objectives: list[dict[str, Any]], source_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "id": "EX1",
            "title": "Complete the core workflow",
            "learner_segment_id": "customer_practitioners",
            "scenario": f"A {context['target_user']} needs to complete {context['primary_scope']}.",
            "task": f"Run the workflow end to end and capture the result for {context['first_milestone']}.",
            "debrief_prompt": "Where did the workflow match or differ from the learner's current process?",
            "learning_objective_ids": ["LO1", "LO2"],
            "source_idea_ids": source_ids,
        },
        {
            "id": "EX2",
            "title": "Interpret adoption evidence",
            "learner_segment_id": "customer_sponsors",
            "scenario": "A sponsor reviews whether the trained cohort is ready to continue.",
            "task": f"Use the success rubric to decide whether {context['first_milestone']} is complete.",
            "debrief_prompt": "What evidence would make the sponsor expand, revise, or pause adoption?",
            "learning_objective_ids": ["LO3", "LO4"],
            "source_idea_ids": source_ids,
        },
        {
            "id": "EX3",
            "title": "Coach and escalate",
            "learner_segment_id": "internal_gtm_support",
            "scenario": "A learner is blocked during first use and asks for help.",
            "task": "Explain the value, identify the blocker, and choose the support or product escalation path.",
            "debrief_prompt": "Which blocker belongs in documentation, support workflow, or product backlog?",
            "learning_objective_ids": [objective["id"] for objective in objectives],
            "source_idea_ids": source_ids,
        },
    ]


def _success_checks(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    exercises: list[dict[str, Any]],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    return [
        {
            "id": "SC1",
            "check": f"{context['target_user']} can complete {context['primary_scope']}.",
            "passing_signal": "At least one customer practitioner completes EX1 without unplanned facilitator action.",
            "exercise_ids": ["EX1"],
            "source_idea_ids": source_ids,
            "source_fields": ["specific_user", "mvp_scope"],
        },
        {
            "id": "SC2",
            "check": "Sponsors can interpret whether adoption should continue.",
            "passing_signal": f"Sponsor decision references {context['first_milestone']} and the validation rubric.",
            "exercise_ids": ["EX2"],
            "source_idea_ids": source_ids,
            "source_fields": ["first_milestones", "validation_plan"],
        },
        {
            "id": "SC3",
            "check": "Internal teams can coach, document, and escalate first-use friction.",
            "passing_signal": "Internal learners classify each exercise blocker with an owner and follow-up path.",
            "exercise_ids": [exercise["id"] for exercise in exercises],
            "source_idea_ids": source_ids,
            "source_fields": ["risks", "validation_plan"],
        },
        {
            "id": "SC4",
            "check": "Training is ready for repeat delivery.",
            "passing_signal": _first_text(
                design_brief.get("validation_plan"),
                "Facilitator records outcomes, open questions, and material updates after the session.",
            ),
            "exercise_ids": [exercise["id"] for exercise in exercises],
            "source_idea_ids": source_ids,
            "source_fields": ["validation_plan"],
        },
    ]


def _follow_up_materials(context: dict[str, Any], source_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": "FM1",
            "name": "Practitioner quick reference",
            "audience": "customer practitioners",
            "purpose": f"Summarize steps and expected outputs for {context['primary_scope']}.",
            "owner": "Customer success",
            "source_idea_ids": source_ids,
        },
        {
            "id": "FM2",
            "name": "Sponsor success rubric",
            "audience": "customer sponsors",
            "purpose": f"Clarify how to evaluate {context['first_milestone']}.",
            "owner": "Product lead",
            "source_idea_ids": source_ids,
        },
        {
            "id": "FM3",
            "name": "Internal coaching notes",
            "audience": "GTM, support, product, and engineering",
            "purpose": "Capture positioning, known blockers, escalation paths, and product follow-ups.",
            "owner": "Support lead",
            "source_idea_ids": source_ids,
        },
    ]


def _gaps_to_resolve(
    design_brief: dict[str, Any], context: dict[str, Any], evidence: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    checks = [
        ("specific_user", "Target learner is not explicit.", "Name the customer practitioner role for training invitations."),
        ("buyer", "Sponsor learner is not explicit.", "Name the sponsor or buyer who will review training outcomes."),
        ("workflow_context", "Training workflow context is not explicit.", "Describe the workflow trigger, inputs, and expected handoff."),
        ("mvp_scope", "Hands-on training scope is not decomposed.", "Select the first task learners must complete in session."),
        ("validation_plan", "Training success rubric is missing.", "Define the pass/fail evidence facilitators should collect."),
    ]
    for field, gap, next_action in checks:
        missing = not _string_list(design_brief.get(field))
        if field in context["fallbacks_used"]:
            missing = True
        if missing:
            gaps.append(
                {
                    "id": f"G{len(gaps) + 1}",
                    "field": field,
                    "gap": gap,
                    "impact": "Training can proceed only as a draft until this is resolved.",
                    "next_action": next_action,
                }
            )

    readiness = float(design_brief.get("readiness_score") or 0.0)
    if readiness < 70:
        gaps.append(
            {
                "id": f"G{len(gaps) + 1}",
                "field": "readiness_score",
                "gap": f"Readiness score is {readiness:.1f}/100.",
                "impact": "Use internal dry runs before customer training.",
                "next_action": "Raise readiness with validation evidence or limit training to internal learners.",
            }
        )
    if not evidence:
        gaps.append(
            {
                "id": f"G{len(gaps) + 1}",
                "field": "evidence_references",
                "gap": "No evidence references support training claims.",
                "impact": "Facilitators lack proof points for value, risks, and success checks.",
                "next_action": "Attach validation plan, rationale, evidence signals, or insights before customer delivery.",
            }
        )
    return gaps


def _next_actions(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"NA{index}",
            "gap_id": gap["id"],
            "owner": _owner_for_gap(gap["field"]),
            "action": gap["next_action"],
        }
        for index, gap in enumerate(gaps, start=1)
    ]


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
                    "summary": f"Evidence signal linked to source idea {idea['id']}.",
                    "source_idea_ids": [idea["id"]],
                }
            )
        for insight_id in _string_list(idea.get("inspiring_insights")):
            refs.append(
                {
                    "id": insight_id,
                    "type": "insight",
                    "summary": f"Inspiring insight linked to source idea {idea['id']}.",
                    "source_idea_ids": [idea["id"]],
                }
            )
    return _dedupe_refs(refs)


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


def _owner_for_gap(field: str) -> str:
    return {
        "buyer": "Product lead",
        "specific_user": "Customer success",
        "workflow_context": "Product lead",
        "mvp_scope": "Product engineering",
        "validation_plan": "Product lead",
        "readiness_score": "Product lead",
        "evidence_references": "Research lead",
    }.get(field, "Product lead")


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


def _field_values(items: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for item in items:
        if item.get("missing"):
            continue
        values.extend(_string_list(item.get(field)))
    return _dedupe_strings(values)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            text = _first_text(*value)
        else:
            text = _compact(value)
        if text:
            return text
    return ""


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(_compact(value) for value in values if _compact(value)))


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for ref in refs:
        deduped.setdefault(ref["id"], ref)
    return list(deduped.values())


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
