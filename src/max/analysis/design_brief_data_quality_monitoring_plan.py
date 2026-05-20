"""Deterministic data quality monitoring plans for persisted design briefs."""

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

KIND = "max.design_brief.data_quality_monitoring_plan"
SCHEMA_VERSION = "max.design_brief.data_quality_monitoring_plan.v1"
CSV_COLUMNS = DEFAULT_CSV_COLUMNS
SECTIONS = (
    "critical_data_assumptions",
    "quality_checks",
    "freshness_checks",
    "anomaly_triggers",
    "ownership",
    "remediation_actions",
)


def build_design_brief_data_quality_monitoring_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build data quality monitoring guidance from a persisted design brief."""
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None

    context = brief_context(store, brief)
    source_id = context["primary_source_idea_id"]
    severity = "high" if context["readiness_score"] < 60 or context["risks"] else "medium"
    risk = context["risks"][0] if context["risks"] else "no explicit data quality risk captured"
    scope_text = ", ".join(context["mvp_scope"])
    evidence = context["evidence"][0] if context["evidence"] else context["workflow_context"]

    assumptions = [
        _row("DA1", "Workflow data is complete", "Product lead", severity, f"{context['workflow_context']} events are captured for every trained or active user.", evidence, source_id),
        _row("DA2", "MVP scope has stable identifiers", "Engineering lead", "medium", f"Records needed for {scope_text} have durable IDs and timestamps.", scope_text, source_id),
        _row("DA3", "Customer-visible data is permitted", "Data owner", "high" if "privacy" in risk.lower() or "security" in risk.lower() else "medium", f"Data used to prove {context['product_concept']} is approved for monitoring.", risk, source_id),
    ]
    checks = [
        _row("QC1", "Required field completeness", "Data owner", severity, "Alert when required workflow fields fall below 98% completeness.", "Completeness >= 98%.", source_id),
        _row("QC2", "Reference integrity", "Engineering lead", "medium", "Validate source, customer, and workflow IDs resolve to known entities.", "Broken references remain at zero for launch-critical paths.", source_id),
        _row("QC3", "Evidence traceability", "Product analyst", "medium", f"Sample records can be traced to {context['evidence_count']} source evidence item(s) or brief assumptions.", evidence, source_id),
    ]
    freshness = [
        _row("FR1", "Workflow freshness", "Data owner", severity, f"{context['workflow_context']} monitoring updates within one business day.", "Last successful ingest <= 24 business hours.", source_id),
        _row("FR2", "Readiness review freshness", "Product lead", "medium", "Brief readiness and risk dispositions are reviewed before each release decision.", f"Current readiness score: {context['readiness_score']:.1f}.", source_id),
    ]
    anomalies = [
        _row("AT1", "Volume deviation", "Product analyst", severity, "Trigger review when workflow volume changes by more than 30% from the prior comparable period.", "Volume delta > 30%.", source_id),
        _row("AT2", "Risk-correlated defects", "Support owner", "high" if context["risks"] else "medium", f"Trigger incident review when defects mention {risk}.", risk, source_id),
    ]
    ownership = [
        _row("OW1", "Data steward", "Data owner", "medium", "Own field definitions, quality thresholds, and monitoring review notes.", "Named steward appears in launch checklist.", source_id),
        _row("OW2", "Remediation approver", context["buyer"], severity, "Approve customer-facing explanations when data quality affects reported outcomes.", context["buyer"], source_id),
    ]
    remediation = [
        _row("RA1", "Pause reporting", "Product lead", severity, "Pause customer-facing reporting when a critical assumption or freshness check fails.", "Customer report is marked pending until corrected.", source_id),
        _row("RA2", "Backfill and reconcile", "Engineering lead", "medium", "Backfill affected records and attach reconciliation notes to the monitoring review.", "Backfill job ID and sampled validation results.", source_id),
        _row("RA3", "Risk disposition", "Risk owner", "high" if context["risks"] else "medium", f"Record mitigation or acceptance for {risk}.", risk, source_id),
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": design_brief_block(brief, context),
        "summary": {
            "monitoring_goal": f"Keep data trustworthy for {context['product_concept']} decisions.",
            "workflow_context": context["workflow_context"],
            "source_evidence_count": context["evidence_count"],
            "primary_risk": risk,
            "fallbacks_used": context["fallbacks_used"],
            "critical_assumption_count": len(assumptions),
            "quality_check_count": len(checks),
            "freshness_check_count": len(freshness),
            "anomaly_trigger_count": len(anomalies),
        },
        "critical_data_assumptions": assumptions,
        "quality_checks": checks,
        "freshness_checks": freshness,
        "anomaly_triggers": anomalies,
        "ownership": ownership,
        "remediation_actions": remediation,
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_data_quality_monitoring_plan(
    report: dict[str, Any], fmt: str = "json"
) -> str:
    """Render a data quality monitoring plan as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_sectioned_csv(report, SECTIONS, CSV_COLUMNS)
    if fmt != "markdown":
        raise ValueError(f"Unsupported data quality monitoring plan format: {fmt}")
    return render_sectioned_markdown(
        report,
        title="Data Quality Monitoring Plan",
        summary_title="Monitoring Summary",
        sections=(
            ("critical_data_assumptions", "Critical Data Assumptions"),
            ("quality_checks", "Quality Checks"),
            ("freshness_checks", "Freshness Checks"),
            ("anomaly_triggers", "Anomaly Triggers"),
            ("ownership", "Ownership"),
            ("remediation_actions", "Remediation Actions"),
        ),
    )


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
