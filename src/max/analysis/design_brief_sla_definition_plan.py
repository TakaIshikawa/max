"""Deterministic SLA definition plans for persisted design briefs."""

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

KIND = "max.design_brief.sla_definition_plan"
SCHEMA_VERSION = "max.design_brief.sla_definition_plan.v1"
CSV_COLUMNS = DEFAULT_CSV_COLUMNS
SECTIONS = (
    "service_promises",
    "measurable_indicators",
    "exclusions",
    "escalation_thresholds",
    "review_cadence",
    "customer_facing_wording",
)


def build_design_brief_sla_definition_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build SLA definition guidance from a persisted design brief."""
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None

    context = brief_context(store, brief)
    source_id = context["primary_source_idea_id"]
    risk = context["risks"][0] if context["risks"] else "service expectations are not yet validated"
    severity = _severity(context["readiness_score"], bool(context["risks"]))
    first_response = "1 business hour" if severity == "high" else "4 business hours"
    resolution = "1 business day" if severity == "high" else "3 business days"
    uptime = "99.5%" if severity == "high" else "99.0%"

    promises = [
        _row("SP1", "Workflow availability", "Product owner", severity, f"Keep {context['workflow_context']} available for trained customer users during agreed business hours.", f"Target availability {uptime}.", source_id),
        _row("SP2", "Support responsiveness", "Support owner", severity, f"Respond to launch-impacting issues for {context['target_user']} within {first_response}.", f"First response <= {first_response}.", source_id),
        _row("SP3", "Scope clarity", "Account owner", "medium", f"Promise applies to MVP scope only: {', '.join(context['mvp_scope'])}.", "Out-of-scope requests are routed to product review.", source_id),
    ]
    indicators = [
        _row("MI1", "Availability", "Engineering lead", severity, "Measure successful workflow checks divided by scheduled checks.", f"Target >= {uptime}.", source_id),
        _row("MI2", "First response time", "Support owner", severity, "Measure time from customer ticket creation to first qualified response.", f"Threshold <= {first_response}.", source_id),
        _row("MI3", "Resolution time", "Support owner", severity, "Measure time from ticket creation to accepted workaround or fix.", f"Threshold <= {resolution}.", source_id),
    ]
    exclusions = [
        _row("EX1", "Unvalidated scope", "Product owner", "medium", "Exclude workflows outside the current design brief MVP scope.", ", ".join(context["mvp_scope"]), source_id),
        _row("EX2", "Customer-controlled dependencies", "Account owner", "medium", "Exclude outages caused by customer credentials, networks, or unavailable upstream data.", "Customer dependency noted in ticket.", source_id),
        _row("EX3", "Accepted risk windows", "Risk owner", severity, f"Exclude explicitly accepted risk windows tied to {risk} only when documented in advance.", risk, source_id),
    ]
    thresholds = [
        _row("ET1", "Severity 1 escalation", "Support owner", "high", f"Escalate immediately when {context['workflow_context']} is unavailable for active customers.", "Page engineering and notify account owner.", source_id),
        _row("ET2", "Severity 2 escalation", "Support owner", severity, f"Escalate when {risk} affects repeated customer tasks or misses {first_response}.", risk, source_id),
        _row("ET3", "Sponsor escalation", "Account owner", severity, f"Escalate to {context['buyer']} when resolution exceeds {resolution}.", context["buyer"], source_id),
    ]
    cadence = [
        _row("RC1", "Launch review", "Product owner", severity, "Review SLA performance weekly for the first month after launch.", "Weekly launch SLA note.", source_id),
        _row("RC2", "Steady-state review", "Account owner", "medium", "Review customer-facing wording and thresholds monthly or after any severity 1 incident.", "Monthly customer success review.", source_id),
    ]
    wording = [
        _row("CW1", "Customer promise", "Account owner", severity, f"We support {context['workflow_context']} for trained users and respond to critical issues within {first_response}.", f"Response promise: {first_response}.", source_id),
        _row("CW2", "Scope wording", "Product owner", "medium", f"This SLA covers the agreed MVP capabilities for {context['product_concept']} and excludes unapproved custom workflows.", context["product_concept"], source_id),
        _row("CW3", "Risk wording", "Risk owner", severity, f"If {risk} occurs, we will notify affected customers with impact, owner, and next update timing.", risk, source_id),
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": design_brief_block(brief, context),
        "summary": {
            "sla_goal": f"Define measurable service expectations for {context['product_concept']}.",
            "severity_recommendation": severity,
            "first_response_threshold": first_response,
            "resolution_threshold": resolution,
            "fallbacks_used": context["fallbacks_used"],
            "service_promise_count": len(promises),
            "indicator_count": len(indicators),
            "escalation_threshold_count": len(thresholds),
        },
        "service_promises": promises,
        "measurable_indicators": indicators,
        "exclusions": exclusions,
        "escalation_thresholds": thresholds,
        "review_cadence": cadence,
        "customer_facing_wording": wording,
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_sla_definition_plan(
    report: dict[str, Any], fmt: str = "json"
) -> str:
    """Render an SLA definition plan as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_sectioned_csv(report, SECTIONS, CSV_COLUMNS)
    if fmt != "markdown":
        raise ValueError(f"Unsupported SLA definition plan format: {fmt}")
    return render_sectioned_markdown(
        report,
        title="SLA Definition Plan",
        summary_title="SLA Summary",
        sections=(
            ("service_promises", "Service Promises"),
            ("measurable_indicators", "Measurable Indicators"),
            ("exclusions", "Exclusions"),
            ("escalation_thresholds", "Escalation Thresholds"),
            ("review_cadence", "Review Cadence"),
            ("customer_facing_wording", "Customer-Facing Wording"),
        ),
    )


def _severity(readiness: float, has_risk: bool) -> str:
    if readiness < 65 or has_risk:
        return "high"
    if readiness < 80:
        return "medium"
    return "standard"


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
