"""Deterministic customer training plans for persisted design briefs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from max.analysis._design_brief_plan_common import (
    DEFAULT_CSV_COLUMNS,
    brief_context,
    design_brief_block,
    render_sectioned_csv,
    render_sectioned_markdown,
    source_block,
)

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.customer_training_plan"
SCHEMA_VERSION = "max.design_brief.customer_training_plan.v1"
CSV_COLUMNS = DEFAULT_CSV_COLUMNS
SECTIONS = (
    "learner_segments",
    "training_modules",
    "prerequisite_setup",
    "practice_exercises",
    "completion_signals",
    "post_training_followups",
)


def build_design_brief_customer_training_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build a customer training plan from a persisted design brief."""
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None

    context = brief_context(store, brief)
    risk_label = context["risks"][0] if context["risks"] else "adoption confusion after training"
    scope_text = ", ".join(context["mvp_scope"])
    source_id = context["primary_source_idea_id"]

    learner_segments = [
        {
            "id": "LS1",
            "name": "Primary workflow learners",
            "owner": "Customer success",
            "action": f"Train {context['target_user']} to complete {context['workflow_context']}.",
            "evidence": context["workflow_context"],
            "source_idea_id": source_id,
        },
        {
            "id": "LS2",
            "name": "Sponsor reviewers",
            "owner": "Account owner",
            "action": f"Show {context['buyer']} how to evaluate outcomes and escalation paths.",
            "evidence": context["buyer"],
            "source_idea_id": source_id,
        },
    ]

    modules = [
        {
            "id": "TM1",
            "name": "Workflow orientation",
            "owner": "Customer success",
            "timing": "30 minutes",
            "action": f"Explain when to use {context['product_concept']} in {context['workflow_context']}.",
            "evidence": context["target_user"],
            "source_idea_id": source_id,
        },
        {
            "id": "TM2",
            "name": "MVP task walkthrough",
            "owner": "Product specialist",
            "timing": "45 minutes",
            "action": f"Walk through the in-scope behavior: {scope_text}.",
            "evidence": scope_text,
            "source_idea_id": source_id,
        },
        {
            "id": "TM3",
            "name": "Risk and support handling",
            "owner": "Support owner",
            "timing": "20 minutes",
            "action": f"Teach learners how to recognize and escalate {risk_label}.",
            "evidence": risk_label,
            "severity": "high" if context["risks"] else "medium",
            "source_idea_id": source_id,
        },
    ]

    setup = [
        {
            "id": "PS1",
            "name": "Customer environment access",
            "owner": "Implementation lead",
            "timing": "Before session",
            "action": f"Provision sample access for {context['target_user']} with the MVP scope enabled.",
            "evidence": "Login succeeds and scoped data is available.",
            "source_idea_id": source_id,
        },
        {
            "id": "PS2",
            "name": "Training scenario packet",
            "owner": "Customer success",
            "timing": "Before session",
            "action": f"Prepare a scenario based on {context['workflow_context']}.",
            "evidence": "Scenario includes starting state, expected output, and escalation contact.",
            "source_idea_id": source_id,
        },
    ]

    exercises = [
        {
            "id": "EX1",
            "name": "Complete first value workflow",
            "owner": "Learner",
            "action": f"Use the product to complete {context['workflow_context']} without facilitator rescue.",
            "evidence": "Learner reaches the expected workflow output.",
            "source_idea_id": source_id,
        },
        {
            "id": "EX2",
            "name": "Handle exception path",
            "owner": "Learner",
            "action": f"Respond to a simulated issue related to {risk_label}.",
            "evidence": "Learner selects the documented support or escalation route.",
            "severity": "high" if context["risks"] else "medium",
            "source_idea_id": source_id,
        },
    ]

    signals = [
        {
            "id": "CS1",
            "name": "Workflow completion",
            "owner": "Customer success",
            "action": "Confirm each learner can complete the primary task from memory.",
            "evidence": "80% or more complete the practice exercise without critical help.",
            "source_idea_id": source_id,
        },
        {
            "id": "CS2",
            "name": "Sponsor readiness",
            "owner": "Account owner",
            "action": f"Confirm {context['buyer']} can state value, limits, and next support step.",
            "evidence": "Sponsor signs off on training completion notes.",
            "source_idea_id": source_id,
        },
    ]

    followups = [
        {
            "id": "FU1",
            "name": "Office hours",
            "owner": "Customer success",
            "timing": "1 week after training",
            "action": "Review learner questions, unresolved blockers, and feature confusion.",
            "evidence": "Office-hours notes are tagged to module or exercise.",
            "source_idea_id": source_id,
        },
        {
            "id": "FU2",
            "name": "Adoption review",
            "owner": "Account owner",
            "timing": "30 days after training",
            "action": f"Compare trained usage with the intended {context['workflow_context']} outcome.",
            "evidence": "Sponsor receives adoption summary and recommended next step.",
            "source_idea_id": source_id,
        },
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": design_brief_block(brief, context),
        "summary": {
            "training_goal": f"Enable customer learners to adopt {context['product_concept']} safely.",
            "target_user": context["target_user"],
            "workflow_context": context["workflow_context"],
            "mvp_scope": context["mvp_scope"],
            "primary_risk": risk_label,
            "fallbacks_used": context["fallbacks_used"],
            "learner_segment_count": len(learner_segments),
            "training_module_count": len(modules),
            "practice_exercise_count": len(exercises),
        },
        "learner_segments": learner_segments,
        "training_modules": modules,
        "prerequisite_setup": setup,
        "practice_exercises": exercises,
        "completion_signals": signals,
        "post_training_followups": followups,
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_customer_training_plan(
    report: dict[str, Any], fmt: str = "json"
) -> str:
    """Render a customer training plan as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_sectioned_csv(report, SECTIONS, CSV_COLUMNS)
    if fmt != "markdown":
        raise ValueError(f"Unsupported customer training plan format: {fmt}")
    return render_sectioned_markdown(
        report,
        title="Customer Training Plan",
        summary_title="Training Summary",
        sections=(
            ("learner_segments", "Learner Segments"),
            ("training_modules", "Training Modules"),
            ("prerequisite_setup", "Prerequisite Setup"),
            ("practice_exercises", "Practice Exercises"),
            ("completion_signals", "Completion Signals"),
            ("post_training_followups", "Post-Training Followups"),
        ),
    )
