"""Deterministic experiment guardrail plans for persisted design briefs."""

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

KIND = "max.design_brief.experiment_guardrail_plan"
SCHEMA_VERSION = "max.design_brief.experiment_guardrail_plan.v1"
CSV_COLUMNS = DEFAULT_CSV_COLUMNS
SECTIONS = (
    "success_metrics",
    "guardrail_metrics",
    "stop_conditions",
    "rollout_limits",
    "review_checkpoints",
    "owner_actions",
)


def build_design_brief_experiment_guardrail_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build experiment guardrails from a persisted design brief."""
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None

    context = brief_context(store, brief)
    source_id = context["primary_source_idea_id"]
    strictness = _strictness(context["readiness_score"], bool(context["risks"]))
    severity = "high" if strictness == "strict" else "medium"
    risk = context["risks"][0] if context["risks"] else "unexpected customer harm or confusing results"
    rollout_cap = "5% or 10 users, whichever is smaller" if strictness == "strict" else "15% or 25 users, whichever is smaller"
    scope = ", ".join(context["mvp_scope"])

    success = [
        _row("SM1", "Primary workflow success", "Product analyst", severity, f"Measure the share of exposed {context['target_user']} completing {context['workflow_context']}.", "Target improvement is defined before launch.", source_id),
        _row("SM2", "MVP value signal", "Product lead", "medium", f"Measure whether users complete or request more of the MVP scope: {scope}.", scope, source_id),
        _row("SM3", "Evidence lift", "Research lead", "medium", f"Collect evidence that improves or rejects the brief assumptions for {context['product_concept']}.", f"Starts with {context['evidence_count']} evidence item(s).", source_id),
    ]
    guardrails = [
        _row("GM1", "Support burden", "Support owner", severity, "Track support tickets, confused-user sessions, and manual rescue events.", "No more than two unresolved high-impact issues.", source_id),
        _row("GM2", "Risk trigger", "Risk owner", "high" if context["risks"] else "medium", f"Track any customer or operational signal tied to {risk}.", risk, source_id),
        _row("GM3", "Performance or reliability", "Engineering lead", severity, f"Track latency, failures, and data freshness for {context['workflow_context']}.", "No sustained degradation versus baseline.", source_id),
    ]
    stops = [
        _row("SC1", "Critical customer harm", "Product lead", "high", f"Stop immediately if {risk} affects active customers or trust.", "Experiment paused and owner notified.", source_id),
        _row("SC2", "Support overload", "Support owner", severity, "Stop expansion when unresolved support issues exceed the guardrail threshold.", "Expansion disabled until support owner clears.", source_id),
        _row("SC3", "Invalid measurement", "Product analyst", severity, "Stop if success or guardrail metrics cannot be measured for the exposed cohort.", "Instrumentation fix required before restart.", source_id),
    ]
    limits = [
        _row("RL1", "Initial exposure cap", "Product lead", severity, f"Limit first exposure to {rollout_cap}.", rollout_cap, source_id),
        _row("RL2", "Scope cap", "Engineering lead", "medium", f"Limit experiment behavior to {scope}.", scope, source_id),
        _row("RL3", "Expansion rule", "Product lead", severity, "Expand only after one checkpoint passes all success and guardrail reviews.", "No stop condition triggered.", source_id),
    ]
    checkpoints = [
        _row("RC1", "Pre-launch review", "Product lead", severity, "Confirm metrics, owners, sample cap, and stop-condition authority.", "Decision record approved.", source_id),
        _row("RC2", "Early signal review", "Product analyst", severity, "Review success and guardrail metrics after the first meaningful usage window.", "Keep, adjust, or stop decision.", source_id),
        _row("RC3", "Final learning review", "Research lead", "medium", "Update design brief evidence, risks, and next experiment recommendation.", "Brief disposition recorded.", source_id),
    ]
    actions = [
        _row("OA1", "Product action", "Product lead", severity, "Own exposure decisions and customer impact tradeoffs.", "Decision record links to guardrail report.", source_id),
        _row("OA2", "Engineering action", "Engineering lead", severity, "Own instrumentation, rollback switch, and reliability fixes.", "Rollback switch tested before exposure.", source_id),
        _row("OA3", "Customer action", "Customer success", "medium", "Notify impacted customers and capture qualitative feedback.", "Feedback tagged by cohort and workflow.", source_id),
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": design_brief_block(brief, context),
        "summary": {
            "guardrail_goal": f"Run experiments for {context['product_concept']} without exceeding customer or operational risk.",
            "strictness": strictness,
            "rollout_cap": rollout_cap,
            "primary_risk": risk,
            "fallbacks_used": context["fallbacks_used"],
            "success_metric_count": len(success),
            "guardrail_metric_count": len(guardrails),
            "stop_condition_count": len(stops),
        },
        "success_metrics": success,
        "guardrail_metrics": guardrails,
        "stop_conditions": stops,
        "rollout_limits": limits,
        "review_checkpoints": checkpoints,
        "owner_actions": actions,
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_experiment_guardrail_plan(
    report: dict[str, Any], fmt: str = "json"
) -> str:
    """Render an experiment guardrail plan as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_sectioned_csv(report, SECTIONS, CSV_COLUMNS)
    if fmt != "markdown":
        raise ValueError(f"Unsupported experiment guardrail plan format: {fmt}")
    return render_sectioned_markdown(
        report,
        title="Experiment Guardrail Plan",
        summary_title="Guardrail Summary",
        sections=(
            ("success_metrics", "Success Metrics"),
            ("guardrail_metrics", "Guardrail Metrics"),
            ("stop_conditions", "Stop Conditions"),
            ("rollout_limits", "Rollout Limits"),
            ("review_checkpoints", "Review Checkpoints"),
            ("owner_actions", "Owner Actions"),
        ),
    )


def _strictness(readiness: float, has_risk: bool) -> str:
    return "strict" if readiness < 70 or has_risk else "standard"


def _row(
    item_id: str,
    name: str,
    owner: str,
    severity: str,
    action: str,
    evidence: str,
    source_idea_id: str,
) -> dict[str, str]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "severity": severity,
        "action": action,
        "evidence": evidence,
        "source_idea_id": source_idea_id,
    }
