"""Deterministic pricing experiment plans for persisted design briefs."""

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

KIND = "max.design_brief.pricing_experiment_plan"
SCHEMA_VERSION = "max.design_brief.pricing_experiment_plan.v1"


def build_design_brief_pricing_experiment_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None
    context = brief_context(store, brief)
    evidence_references = _evidence_references(brief, context)
    evidence_gaps = _evidence_gaps(context, brief)
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
            "pricing_posture": "pricing_discovery_required" if evidence_gaps else "ready_for_pricing_experiment",
            "hypothesis_count": 2,
            "evidence_gap_count": len(evidence_gaps),
            "fallbacks_used": context["fallbacks_used"],
        },
        "pricing_hypotheses": _pricing_hypotheses(context),
        "value_metric_candidates": _value_metric_candidates(context, brief),
        "target_segments": _target_segments(context),
        "experiment_stages": _experiment_stages(context),
        "guardrail_metrics": _guardrail_metrics(context),
        "decision_rules": _decision_rules(context),
        "evidence_references": evidence_references,
        "evidence_gaps": evidence_gaps,
        "open_questions": _open_questions(context, evidence_gaps),
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_pricing_experiment_plan(
    report: dict[str, Any], fmt: str = "markdown"
) -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported pricing experiment plan format: {fmt}")
    brief = report["design_brief"]
    lines = [
        f"# Pricing Experiment Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
    ]
    for key, title in (
        ("pricing_hypotheses", "Pricing Hypotheses"),
        ("value_metric_candidates", "Value Metric Candidates"),
        ("target_segments", "Target Segments"),
        ("experiment_stages", "Experiment Stages"),
        ("guardrail_metrics", "Guardrail Metrics"),
        ("decision_rules", "Decision Rules"),
        ("evidence_gaps", "Evidence Gaps"),
        ("open_questions", "Open Questions"),
    ):
        lines.extend(["", f"## {title}", ""])
        rows = report.get(key) or []
        if not rows:
            lines.append("- None")
        for row in rows:
            label = row.get("name") or row.get("question") or row.get("id")
            detail = row.get("description") or row.get("rule") or row.get("question") or row.get("measurement")
            lines.append(f"- **{row['id']} {label}**: {detail}")
    return "\n".join(lines).rstrip() + "\n"


def pricing_experiment_plan_filename(
    design_brief: dict[str, Any], fmt: str = "markdown"
) -> str:
    extension = {"json": "json", "markdown": "md"}.get(fmt, "md")
    return (
        f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-"
        f"{_filename_part(str(design_brief.get('title') or 'Pricing Experiment Plan'))}-"
        f"pricing-experiment-plan.{extension}"
    )


def _pricing_hypotheses(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"id": "H1", "name": "Workflow value pricing", "description": f"{context['buyer']} will pay for measurable improvement in {context['workflow_context']}.", "evidence": join_text(context["evidence"], "willingness-to-pay evidence pending")},
        {"id": "H2", "name": "MVP packaging", "description": f"Package {join_text(context['mvp_scope'], 'the MVP scope')} as the smallest paid tier or add-on.", "evidence": context["primary_source_idea_id"]},
    ]


def _value_metric_candidates(context: dict[str, Any], brief: dict[str, Any]) -> list[dict[str, str]]:
    blob = text(brief).lower() + " " + text(context["source_ideas"]).lower()
    metric = "active workflow"
    if "seat" in blob or "user" in blob:
        metric = "active user"
    if "api" in blob or "integration" in blob:
        metric = "connected integration"
    if "usage" in blob or "volume" in blob:
        metric = "usage volume"
    return [
        {"id": "V1", "name": metric, "description": f"Charge or meter by {metric} tied to {context['workflow_context']}.", "measurement": metric},
        {"id": "V2", "name": "activated account", "description": "Use activated account as a simple packaging threshold.", "measurement": "activated account count"},
    ]


def _target_segments(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"id": "S1", "name": context["buyer"], "description": f"Buyer segment sponsoring {context['target_user']} in {context['workflow_context']}."}
    ]


def _experiment_stages(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"id": "E1", "name": "Qualitative pricing discovery", "description": "Test problem severity, alternatives, budget owner, and willingness-to-pay language."},
        {"id": "E2", "name": "Packaging smoke test", "description": f"Compare packaging for {join_text(context['mvp_scope'], 'the MVP scope')} with target buyers."},
        {"id": "E3", "name": "Pilot price validation", "description": "Run a quoted pilot or paid beta with explicit acceptance criteria."},
    ]


def _guardrail_metrics(context: dict[str, Any]) -> list[dict[str, str]]:
    risks = context["risks"] or ["pricing friction or buyer confusion"]
    return [
        {"id": "G1", "name": "Activation impact", "measurement": "Activation rate does not decline materially during pricing test."},
        {"id": "G2", "name": "Risk signal", "measurement": join_text(risks[:2], "No explicit risk signal supplied.")},
    ]


def _decision_rules(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"id": "D1", "name": "Proceed", "rule": f"Proceed when {context['buyer']} confirms value metric, budget path, and measurable value."},
        {"id": "D2", "name": "Revise", "rule": "Revise packaging when buyers accept value but reject metric, tier, or guardrails."},
        {"id": "D3", "name": "Stop", "rule": "Stop when no buyer owns the budget or no willingness-to-pay evidence appears."},
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
        for field in ("value_proposition", "buyer", "evidence_signals", "inspiring_insights"):
            values = list_values(idea.get(field))
            if values:
                refs.append({"id": f"{idea['id']}.{field}", "type": field, "description": join_text(values, "")})
    return refs


def _evidence_gaps(context: dict[str, Any], brief: dict[str, Any]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    if "buyer" in context["fallbacks_used"]:
        gaps.append({"id": "missing_buyer", "description": "Buyer or budget owner is missing."})
    if not any(text(idea.get("value_proposition")) for idea in context["source_ideas"] if not idea.get("missing")):
        gaps.append({"id": "missing_value_proposition", "description": "Value proposition evidence is missing."})
    if not text(brief.get("validation_plan")):
        gaps.append({"id": "missing_validation_plan", "description": "Validation plan for pricing experiment is missing."})
    blob = (text(brief) + " " + text(context["source_ideas"])).lower()
    if context["evidence_count"] == 0 or not any(term in blob for term in (" pay", "paid", "budget", "willingness", "$")):
        gaps.append({"id": "missing_willingness_to_pay", "description": "Willingness-to-pay evidence is missing."})
    return gaps


def _open_questions(context: dict[str, Any], gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    questions = [
        {"id": "Q1", "question": f"What budget does {context['buyer']} control for this workflow?"},
        {"id": "Q2", "question": "Which value metric best matches buyer perception and delivery cost?"},
    ]
    questions.extend({"id": f"Q{idx + 2}", "question": gap["description"]} for idx, gap in enumerate(gaps))
    return questions


def _filename_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in cleaned.split("-") if part) or "design-brief"
