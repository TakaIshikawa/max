"""Deterministic experiment rollout readiness plans for persisted design briefs."""

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

KIND = "max.design_brief.experiment_rollout_readiness_plan"
SCHEMA_VERSION = "max.design_brief.experiment_rollout_readiness_plan.v1"


def build_design_brief_experiment_rollout_readiness_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None
    context = brief_context(store, brief)
    refs = _refs(brief, context)
    gaps = _gaps(context, refs)
    decision = _decision(context, gaps)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": {
            **design_brief_block(brief, context),
            "specific_user": context["target_user"],
        },
        "summary": {
            "rollout_posture": decision["status"],
            "evidence_gap_count": len(gaps),
            "fallbacks_used": context["fallbacks_used"],
        },
        "rollout_hypotheses": _hypotheses(context),
        "cohort_plan": _cohort_plan(context),
        "guardrail_checks": _guardrails(context),
        "telemetry_requirements": _telemetry(context),
        "rollout_decision": decision,
        "evidence_references": refs,
        "evidence_gaps": gaps,
        "open_questions": _questions(context, gaps),
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_experiment_rollout_readiness_plan(
    report: dict[str, Any], fmt: str = "markdown"
) -> str:
    return _render(report, fmt, "Experiment Rollout Readiness Plan")


def experiment_rollout_readiness_plan_filename(
    design_brief: dict[str, Any], fmt: str = "markdown"
) -> str:
    return _filename(
        design_brief, "Experiment Rollout Readiness Plan", "experiment-rollout-readiness-plan", fmt
    )


def _hypotheses(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "H1",
            "name": "Workflow value hypothesis",
            "owner": "Product owner",
            "evidence": context["product_concept"],
            "action": f"{context['target_user']} will complete {context['workflow_context']} with less friction.",
        }
    ]


def _cohort_plan(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "C1",
            "name": "Initial cohort",
            "owner": context["buyer"],
            "evidence": context["target_user"],
            "action": f"Start with a limited {context['target_user']} cohort before expansion.",
        }
    ]


def _guardrails(context: dict[str, Any]) -> list[dict[str, str]]:
    risks = context["risks"] or ["No guardrail risk evidence captured."]
    return [
        {
            "id": f"G{i}",
            "name": "Rollout guardrail",
            "owner": "Experiment owner",
            "severity": "high"
            if _has(risk, ("risk", "security", "privacy", "failure"))
            else "medium",
            "evidence": risk,
            "action": f"Pause rollout if guardrail is breached: {risk}",
        }
        for i, risk in enumerate(risks, 1)
    ]


def _telemetry(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "T1",
            "name": "Activation and success metrics",
            "owner": "Analytics owner",
            "evidence": join_text(context["evidence"], "Telemetry evidence missing"),
            "action": "Measure activation, success, failure, and rollback triggers.",
        }
    ]


def _decision(context: dict[str, Any], gaps: list[dict[str, str]]) -> dict[str, str]:
    blob = _blob(context)
    status = (
        "ready_for_limited_rollout"
        if _has(blob, ("validation", "telemetry", "metric", "cohort", "experiment")) and not gaps
        else "blocked_pending_rollout_evidence"
    )
    return {
        "status": status,
        "owner": context["buyer"],
        "rationale": f"{len(gaps)} rollout evidence gap(s) remain.",
    }


def _gaps(context: dict[str, Any], refs: list[dict[str, str]]) -> list[dict[str, str]]:
    blob = _blob(context)
    gaps = []
    if not context["product_concept"]:
        gaps.append(
            {
                "id": "missing_hypothesis",
                "description": "Experiment hypothesis evidence is missing.",
            }
        )
    if "specific_user" in context["fallbacks_used"]:
        gaps.append({"id": "missing_cohort", "description": "Cohort evidence is missing."})
    if not _has(blob, ("telemetry", "metric", "dashboard", "instrument")):
        gaps.append({"id": "missing_telemetry", "description": "Telemetry evidence is missing."})
    if not context["risks"] and not refs:
        gaps.append({"id": "missing_guardrail", "description": "Guardrail evidence is missing."})
    return gaps


def _questions(context: dict[str, Any], gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "id": "Q1",
            "question": f"What success threshold promotes {context['product_concept']} beyond the first cohort?",
        }
    ] + [{"id": f"QG{i}", "question": gap["description"]} for i, gap in enumerate(gaps, 1)]


def _refs(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    refs = _brief_refs(brief, ("validation_plan", "risks", "first_milestones"))
    refs.extend(_idea_refs(context, ("evidence_signals", "domain_risks", "workflow_context")))
    return refs


def _blob(context: dict[str, Any]) -> str:
    return " ".join(
        [text(context["source_ideas"]), *context["risks"], *context["evidence"]]
    ).lower()


def _has(value: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in value for keyword in keywords)


def _render(report: dict[str, Any], fmt: str, title: str) -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported {title.lower()} format: {fmt}")
    brief = report["design_brief"]
    lines = [
        f"# {title}: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
    ]
    for key in (
        "rollout_hypotheses",
        "cohort_plan",
        "guardrail_checks",
        "telemetry_requirements",
        "evidence_gaps",
    ):
        lines.extend(["", f"## {key.replace('_', ' ').title()}", ""])
        rows = report.get(key) or []
        lines.extend(
            f"- **{row['id']} {row.get('name', row['id'])}**: {row.get('action') or row.get('description')}"
            for row in rows
        ) if rows else lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def _brief_refs(brief: dict[str, Any], fields: tuple[str, ...]) -> list[dict[str, str]]:
    return [
        {
            "id": f"design_brief.{field}",
            "type": field,
            "description": join_text(list_values(brief.get(field)), ""),
        }
        for field in fields
        if list_values(brief.get(field))
    ]


def _idea_refs(context: dict[str, Any], fields: tuple[str, ...]) -> list[dict[str, str]]:
    refs = []
    for idea in context["source_ideas"]:
        if idea.get("missing"):
            continue
        refs.extend(
            {
                "id": f"{idea['id']}.{field}",
                "type": field,
                "description": join_text(list_values(idea.get(field)), ""),
            }
            for field in fields
            if list_values(idea.get(field))
        )
    return refs


def _filename(design_brief: dict[str, Any], default_title: str, suffix: str, fmt: str) -> str:
    extension = {"json": "json", "markdown": "md"}.get(fmt, "md")
    return f"{_part(str(design_brief.get('id') or 'design-brief'))}-{_part(str(design_brief.get('title') or default_title))}-{suffix}.{extension}"


def _part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in text(value))
    return "-".join(part for part in cleaned.split("-") if part) or "design-brief"
