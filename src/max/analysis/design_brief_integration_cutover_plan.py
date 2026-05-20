"""Deterministic integration cutover plans for persisted design briefs."""

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

KIND = "max.design_brief.integration_cutover_plan"
SCHEMA_VERSION = "max.design_brief.integration_cutover_plan.v1"
CSV_COLUMNS = DEFAULT_CSV_COLUMNS
SECTIONS = (
    "cutover_prerequisites",
    "cutover_sequence",
    "rollback_checkpoints",
    "partner_coordination",
    "verification_probes",
    "customer_communications",
)


def build_design_brief_integration_cutover_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build an integration cutover plan from a persisted design brief."""
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None

    context = brief_context(store, brief)
    source_id = context["primary_source_idea_id"]
    risk = context["risks"][0] if context["risks"] else "integration behavior differs from the brief"
    severity = "high" if context["readiness_score"] < 65 or context["risks"] else "medium"
    scope = ", ".join(context["mvp_scope"])

    prerequisites = [
        _row("PR1", "Scope freeze", "Product lead", "T-5 business days", severity, f"Confirm cutover is limited to {scope}.", scope, source_id),
        _row("PR2", "Partner access", "Engineering lead", "T-4 business days", "medium", f"Confirm credentials, endpoints, and test accounts for {context['workflow_context']}.", context["workflow_context"], source_id),
        _row("PR3", "Risk disposition", "Risk owner", "T-3 business days", severity, f"Record mitigation or acceptance for {risk}.", risk, source_id),
    ]
    sequence = [
        _row("SQ1", "Pre-cutover snapshot", "Engineering lead", "T-1 day", "medium", "Capture current configuration, data counts, and dependency status.", "Snapshot stored with release record.", source_id),
        _row("SQ2", "Enable integration path", "Engineering lead", "Cutover window", severity, f"Enable the integration path for {context['target_user']} and the scoped workflow.", context["target_user"], source_id),
        _row("SQ3", "Monitor first live traffic", "Support owner", "First 2 hours", severity, f"Watch errors, latency, and customer impact for {context['workflow_context']}.", context["workflow_context"], source_id),
    ]
    rollback = [
        _row("RB1", "Configuration checkpoint", "Engineering lead", "After enablement", severity, "Rollback if configuration drift blocks the primary workflow.", "Pre-cutover snapshot can be restored.", source_id),
        _row("RB2", "Customer impact checkpoint", "Customer owner", "First 2 hours", severity, f"Rollback or pause if {risk} affects active customers.", risk, source_id),
    ]
    partners = [
        _row("PC1", "Partner readiness confirmation", "Partner owner", "T-2 business days", "medium", "Confirm partner contacts, escalation channel, and maintenance windows.", "Partner acknowledgement recorded.", source_id),
        _row("PC2", "Joint support channel", "Support owner", "Cutover window", "medium", "Keep engineering, partner, and customer success in one live coordination channel.", "Channel transcript links to cutover record.", source_id),
    ]
    probes = [
        _row("VP1", "Workflow success probe", "QA owner", "Immediately after enablement", severity, f"Run a synthetic transaction through {context['workflow_context']}.", "Probe returns expected output.", source_id),
        _row("VP2", "Data reconciliation probe", "Data owner", "After first batch", "medium", "Compare source and destination counts for scoped records.", "Reconciliation delta is within agreed tolerance.", source_id),
        _row("VP3", "Support path probe", "Support owner", "Before customer notice", "medium", "Open and resolve a test escalation using the launch support path.", "Support ticket has owner, status, and resolution note.", source_id),
    ]
    comms = [
        _row("CC1", "Cutover notice", "Customer success", "T-2 business days", "medium", f"Notify {context['buyer']} of timing, expected impact, and rollback criteria.", context["buyer"], source_id),
        _row("CC2", "Go-live update", "Customer success", "After verification", "medium", f"Tell {context['target_user']} when the integration is live for {context['workflow_context']}.", context["target_user"], source_id),
        _row("CC3", "Issue update", "Customer success", "If rollback or pause occurs", severity, f"Explain customer impact, next step, and owner when {risk} is triggered.", risk, source_id),
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": design_brief_block(brief, context),
        "summary": {
            "cutover_goal": f"Move {context['product_concept']} into the live integration path with controlled rollback.",
            "workflow_context": context["workflow_context"],
            "primary_risk": risk,
            "fallbacks_used": context["fallbacks_used"],
            "prerequisite_count": len(prerequisites),
            "sequence_step_count": len(sequence),
            "verification_probe_count": len(probes),
        },
        "cutover_prerequisites": prerequisites,
        "cutover_sequence": sequence,
        "rollback_checkpoints": rollback,
        "partner_coordination": partners,
        "verification_probes": probes,
        "customer_communications": comms,
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_integration_cutover_plan(
    report: dict[str, Any], fmt: str = "json"
) -> str:
    """Render an integration cutover plan as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_sectioned_csv(report, SECTIONS, CSV_COLUMNS)
    if fmt != "markdown":
        raise ValueError(f"Unsupported integration cutover plan format: {fmt}")
    return render_sectioned_markdown(
        report,
        title="Integration Cutover Plan",
        summary_title="Cutover Summary",
        sections=(
            ("cutover_prerequisites", "Cutover Prerequisites"),
            ("cutover_sequence", "Cutover Sequence"),
            ("rollback_checkpoints", "Rollback Checkpoints"),
            ("partner_coordination", "Partner Coordination"),
            ("verification_probes", "Verification Probes"),
            ("customer_communications", "Customer Communications"),
        ),
    )


def _row(
    item_id: str,
    name: str,
    owner: str,
    timing: str,
    severity: str,
    action: str,
    evidence: str,
    source_idea_id: str,
) -> dict[str, str]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "timing": timing,
        "severity": severity,
        "action": action,
        "evidence": evidence,
        "source_idea_id": source_idea_id,
    }
