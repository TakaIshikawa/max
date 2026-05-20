"""Deterministic trial success plans for persisted design briefs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from max.analysis._design_brief_plan_common import (
    brief_context,
    design_brief_block,
    join_text,
    list_values,
    source_block,
    text,
)

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.trial_success_plan"
SCHEMA_VERSION = "max.design_brief.trial_success_plan.v1"


def build_design_brief_trial_success_plan(store: Store, brief_id: str) -> dict[str, Any] | None:
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None
    context = brief_context(store, brief)
    evidence_references = _evidence_references(brief, context)
    evidence_gaps = _evidence_gaps(context, brief)
    open_questions = _open_questions(context, evidence_gaps)
    trial_objectives = _trial_objectives(context, brief)
    activation_milestones = _activation_milestones(context, brief)
    success_metrics = _success_metrics(context, brief)
    disqualification_signals = _disqualification_signals(context)
    stakeholder_checkpoints = _stakeholder_checkpoints(context, brief)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": {
            **design_brief_block(brief, context),
            "buyer": context["buyer"],
            "specific_user": context["target_user"],
            "workflow_context": context["workflow_context"],
        },
        "summary": {
            "trial_posture": "trial_discovery_required" if evidence_gaps else "ready_for_trial_design",
            "objective_count": len(trial_objectives),
            "activation_milestone_count": len(activation_milestones),
            "success_metric_count": len(success_metrics),
            "evidence_gap_count": len(evidence_gaps),
            "fallbacks_used": context["fallbacks_used"],
        },
        "trial_objectives": trial_objectives,
        "activation_milestones": activation_milestones,
        "success_metrics": success_metrics,
        "disqualification_signals": disqualification_signals,
        "stakeholder_checkpoints": stakeholder_checkpoints,
        "evidence_references": evidence_references,
        "evidence_gaps": evidence_gaps,
        "open_questions": open_questions,
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_trial_success_plan(report: dict[str, Any], fmt: str = "markdown") -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported trial success plan format: {fmt}")
    brief = report["design_brief"]
    lines = [
        f"# Trial Success Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
    ]
    for key, title in (
        ("trial_objectives", "Trial Objectives"),
        ("activation_milestones", "Activation Milestones"),
        ("success_metrics", "Success Metrics"),
        ("disqualification_signals", "Disqualification Signals"),
        ("stakeholder_checkpoints", "Stakeholder Checkpoints"),
        ("evidence_gaps", "Evidence Gaps"),
        ("open_questions", "Open Questions"),
    ):
        lines.extend(["", f"## {title}", ""])
        rows = report.get(key) or []
        if not rows:
            lines.append("- None")
            continue
        for row in rows:
            label = row.get("name") or row.get("question") or row.get("description") or row.get("id")
            details = row.get("description") or row.get("criteria") or row.get("timing") or row.get("question")
            lines.append(f"- **{row['id']} {label}**: {details}")
    return "\n".join(lines).rstrip() + "\n"


def trial_success_plan_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    extension = {"json": "json", "markdown": "md"}.get(fmt, "md")
    return (
        f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-"
        f"{_filename_part(str(design_brief.get('title') or 'Trial Success Plan'))}-"
        f"trial-success-plan.{extension}"
    )


def _trial_objectives(context: dict[str, Any], brief: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "O1",
            "name": "Validate target workflow value",
            "description": f"Confirm {context['target_user']} can use {context['product_concept']} in {context['workflow_context']}.",
            "owner": context["buyer"],
            "evidence": join_text(context["evidence"], text(brief.get("validation_plan"), "validation evidence pending")),
        },
        {
            "id": "O2",
            "name": "Confirm MVP activation",
            "description": f"Prove the trial can activate around {join_text(context['mvp_scope'], 'the minimum testable scope')}.",
            "owner": "Product owner",
            "evidence": join_text(list_values(brief.get("first_milestones")), "activation milestone pending"),
        },
    ]


def _activation_milestones(context: dict[str, Any], brief: dict[str, Any]) -> list[dict[str, str]]:
    milestones = list_values(brief.get("first_milestones")) or context["mvp_scope"]
    return [
        {
            "id": f"M{idx}",
            "name": milestone,
            "description": f"Trial participant completes {milestone}.",
            "owner": "Product owner",
            "evidence": context["primary_source_idea_id"],
        }
        for idx, milestone in enumerate(milestones[:4], start=1)
    ]


def _success_metrics(context: dict[str, Any], brief: dict[str, Any]) -> list[dict[str, str]]:
    validation = text(brief.get("validation_plan"))
    return [
        {
            "id": "S1",
            "name": "Activation completion",
            "criteria": f"At least one target account completes {context['mvp_scope'][0]} without manual rescue.",
            "measurement": "count of completed activation milestones",
        },
        {
            "id": "S2",
            "name": "Validated outcome",
            "criteria": validation or "Measurable outcome is unknown and must be defined before the trial starts.",
            "measurement": "validated learning decision recorded",
        },
    ]


def _disqualification_signals(context: dict[str, Any]) -> list[dict[str, str]]:
    risks = context["risks"] or ["No explicit risks; define failure modes before accepting trial results."]
    return [
        {
            "id": f"D{idx}",
            "name": "Trial disqualification signal",
            "description": risk,
            "severity": "high" if any(word in risk.lower() for word in ("security", "legal", "cannot", "blocked")) else "medium",
        }
        for idx, risk in enumerate(risks[:4], start=1)
    ]


def _stakeholder_checkpoints(context: dict[str, Any], brief: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"id": "C1", "name": "Trial kickoff", "timing": "Before participant onboarding", "owner": context["buyer"]},
        {"id": "C2", "name": "Activation review", "timing": join_text(list_values(brief.get("first_milestones")), "After first milestone"), "owner": "Product owner"},
        {"id": "C3", "name": "Trial decision", "timing": "After validation evidence is reviewed", "owner": context["buyer"]},
    ]


def _evidence_references(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for field in ("validation_plan", "why_this_now", "synthesis_rationale"):
        value = text(brief.get(field))
        if value:
            refs.append({"id": f"design_brief.{field}", "type": field, "description": value})
    for idea in context["source_ideas"]:
        if idea.get("missing"):
            continue
        for field in ("evidence_signals", "inspiring_insights", "validation_plan"):
            values = list_values(idea.get(field))
            if values:
                refs.append({"id": f"{idea['id']}.{field}", "type": field, "description": join_text(values, "")})
    return refs


def _evidence_gaps(context: dict[str, Any], brief: dict[str, Any]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    if not text(brief.get("validation_plan")):
        gaps.append({"id": "missing_validation_plan", "description": "Validation plan is missing for trial success decisions."})
    if "specific_user" in context["fallbacks_used"]:
        gaps.append({"id": "missing_target_user", "description": "Target trial user is missing."})
    if not _has_measurable_outcome(brief, context):
        gaps.append({"id": "missing_measurable_outcome", "description": "Measurable trial outcome is missing."})
    return gaps


def _open_questions(context: dict[str, Any], gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    questions = [
        {"id": "Q1", "question": f"Who signs off that {context['buyer']} accepts the trial outcome?"},
        {"id": "Q2", "question": "What minimum sample size makes the trial decision credible?"},
    ]
    questions.extend({"id": f"Q{idx + 2}", "question": gap["description"]} for idx, gap in enumerate(gaps))
    return questions


def _has_measurable_outcome(brief: dict[str, Any], context: dict[str, Any]) -> bool:
    values = [text(brief.get("validation_plan")), *context["evidence"]]
    return any(any(ch.isdigit() for ch in value) or "measure" in value.lower() for value in values)


def _filename_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in cleaned.split("-") if part) or "design-brief"
