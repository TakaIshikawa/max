"""Deterministic operational acceptance plans for persisted design briefs."""

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

KIND = "max.design_brief.operational_acceptance_plan"
SCHEMA_VERSION = "max.design_brief.operational_acceptance_plan.v1"
CSV_COLUMNS = DEFAULT_CSV_COLUMNS
SECTIONS = (
    "supportability_gates",
    "observability_gates",
    "security_handoff_gates",
    "documentation_gates",
    "launch_ownership_gates",
    "risk_exception_gates",
)


def build_design_brief_operational_acceptance_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build operational acceptance gates from persisted design brief data."""
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None

    context = brief_context(store, brief)
    source_id = context["primary_source_idea_id"]
    readiness = context["readiness_score"]
    warning = _warning(readiness, bool(context["risks"]))
    severity = "high" if warning else "medium"
    risk = context["risks"][0] if context["risks"] else "unresolved launch risk not yet captured"
    scope = ", ".join(context["mvp_scope"])

    support = [
        _row("SG1", "Support playbook ready", "Support owner", severity, f"Support can triage {context['workflow_context']} issues for {context['target_user']}.", "Playbook includes known issues, escalation, and customer-safe wording.", source_id),
        _row("SG2", "Support capacity accepted", "Customer success", severity, "Launch volume and office-hours coverage are accepted by the support owner.", "Named coverage owner and escalation SLA.", source_id),
    ]
    observability = [
        _row("OG1", "Workflow instrumentation", "Engineering lead", severity, f"Dashboards show success, failure, and latency for {context['workflow_context']}.", "Dashboard link and alert owner are recorded.", source_id),
        _row("OG2", "MVP scope monitors", "Product analyst", "medium", f"Metrics distinguish in-scope behavior from out-of-scope requests: {scope}.", scope, source_id),
    ]
    security = [
        _row("SH1", "Security handoff", "Security owner", "high" if _security_risk(risk) else severity, f"Security owner reviews data, access, and exception handling before launch.", risk, source_id),
        _row("SH2", "Access ownership", "Engineering lead", "medium", "Admin access, customer access, and break-glass ownership are documented.", "Access list has owner and review date.", source_id),
    ]
    docs = [
        _row("DG1", "Customer documentation", "Documentation owner", "medium", f"Customer docs explain when and how to use {context['product_concept']}.", context["product_concept"], source_id),
        _row("DG2", "Internal runbook", "Support owner", severity, f"Runbook covers {context['workflow_context']}, rollback, and unresolved risks.", risk, source_id),
    ]
    ownership = [
        _row("LO1", "Launch decision owner", context["buyer"], severity, "Single accountable approver accepts operational readiness before release.", context["buyer"], source_id),
        _row("LO2", "Post-launch owner", "Product lead", "medium", "Owner reviews incidents, adoption, and evidence updates after launch.", "Review date is scheduled.", source_id),
    ]
    exceptions = [
        _row("RE1", "Risk exception review", "Risk owner", "high" if context["risks"] or readiness < 60 else "medium", f"Explicitly accept, mitigate, or block launch for {risk}.", risk, source_id),
        _row("RE2", "Low-readiness warning", "Product lead", "high" if readiness < 60 else "low", warning or "Readiness score does not require elevated acceptance warning.", f"Readiness score {readiness:.1f}.", source_id),
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": design_brief_block(brief, context),
        "summary": {
            "acceptance_goal": f"Confirm {context['product_concept']} can be operated after launch.",
            "readiness_warning": warning,
            "workflow_context": context["workflow_context"],
            "fallbacks_used": context["fallbacks_used"],
            "supportability_gate_count": len(support),
            "observability_gate_count": len(observability),
            "risk_exception_gate_count": len(exceptions),
        },
        "supportability_gates": support,
        "observability_gates": observability,
        "security_handoff_gates": security,
        "documentation_gates": docs,
        "launch_ownership_gates": ownership,
        "risk_exception_gates": exceptions,
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_operational_acceptance_plan(
    report: dict[str, Any], fmt: str = "json"
) -> str:
    """Render an operational acceptance plan as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_sectioned_csv(report, SECTIONS, CSV_COLUMNS)
    if fmt != "markdown":
        raise ValueError(f"Unsupported operational acceptance plan format: {fmt}")
    return render_sectioned_markdown(
        report,
        title="Operational Acceptance Plan",
        summary_title="Acceptance Summary",
        sections=(
            ("supportability_gates", "Supportability Gates"),
            ("observability_gates", "Observability Gates"),
            ("security_handoff_gates", "Security Handoff Gates"),
            ("documentation_gates", "Documentation Gates"),
            ("launch_ownership_gates", "Launch Ownership Gates"),
            ("risk_exception_gates", "Risk Exception Gates"),
        ),
    )


def _warning(readiness: float, has_risk: bool) -> str:
    if readiness < 50:
        return "Readiness below 50 requires executive launch exception."
    if readiness < 70:
        return "Readiness below 70 requires elevated operational acceptance review."
    if has_risk:
        return "Explicit risks require named exception owners before launch."
    return ""


def _security_risk(risk: str) -> bool:
    lower = risk.lower()
    return "security" in lower or "privacy" in lower or "access" in lower


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
