"""Deterministic telemetry quality plans for persisted design briefs."""

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

KIND = "max.design_brief.telemetry_quality_plan"
SCHEMA_VERSION = "max.design_brief.telemetry_quality_plan.v1"


def build_design_brief_telemetry_quality_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build a deterministic telemetry quality plan from a persisted design brief."""
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None

    context = brief_context(store, brief)
    evidence_references = _evidence_references(brief, context)
    telemetry_events = _telemetry_events(brief, context)
    quality_risks = _quality_risks(context, telemetry_events)
    instrumentation_gaps = _instrumentation_gaps(context, brief, evidence_references)
    acceptance_checks = _acceptance_checks(context, telemetry_events, quality_risks)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": {
            **design_brief_block(brief, context),
            "buyer": context["buyer"],
            "specific_user": context["target_user"],
            "workflow_context": context["workflow_context"],
            "measurable_outcome": _measurable_outcome(brief, context),
        },
        "summary": {
            "quality_posture": _quality_posture(instrumentation_gaps, quality_risks),
            "event_count": len(telemetry_events),
            "quality_risk_count": len(quality_risks),
            "instrumentation_gap_count": len(instrumentation_gaps),
            "acceptance_check_count": len(acceptance_checks),
            "evidence_reference_count": len(evidence_references),
            "fallbacks_used": context["fallbacks_used"],
        },
        "telemetry_events": telemetry_events,
        "quality_risks": quality_risks,
        "instrumentation_gaps": instrumentation_gaps,
        "acceptance_checks": acceptance_checks,
        "evidence_references": evidence_references,
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_telemetry_quality_plan(
    report: dict[str, Any], fmt: str = "markdown"
) -> str:
    """Render a telemetry quality plan as deterministic Markdown or JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported telemetry quality plan format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Telemetry Quality Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Quality posture: {summary['quality_posture']}",
        "",
        "## Telemetry Events",
        "",
    ]
    for event in report["telemetry_events"]:
        lines.append(
            f"- **{event['id']} {event['name']}**: category: {event['category']}; "
            f"trigger: {event['trigger']}; metric: {event['metric_linkage']}; "
            f"properties: {join_text(event['required_properties'], 'none')}; "
            f"evidence: {join_text(event['evidence'], 'unknown')}"
        )

    lines.extend(["", "## Quality Risks", ""])
    for risk in report["quality_risks"]:
        lines.append(
            f"- **{risk['id']} {risk['name']}** (`{risk['severity']}`): {risk['description']}; "
            f"mitigation: {risk['mitigation']}"
        )

    lines.extend(["", "## Instrumentation Gaps", ""])
    if report["instrumentation_gaps"]:
        lines.extend(
            f"- **{gap['id']}**: {gap['description']}" for gap in report["instrumentation_gaps"]
        )
    else:
        lines.append("- None")

    lines.extend(["", "## Acceptance Checks", ""])
    for check in report["acceptance_checks"]:
        lines.append(f"- **{check['id']} {check['name']}**: {check['check']}")

    lines.extend(["", "## Evidence References", ""])
    if report["evidence_references"]:
        lines.extend(
            f"- `{item['id']}` ({item['type']}): {item['description']}"
            for item in report["evidence_references"]
        )
    else:
        lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def telemetry_quality_plan_filename(
    design_brief: dict[str, Any], fmt: str = "markdown"
) -> str:
    extension = {"json": "json", "markdown": "md"}.get(fmt, "md")
    return (
        f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-"
        f"{_filename_part(str(design_brief.get('title') or 'Telemetry Quality Plan'))}-"
        f"telemetry-quality-plan.{extension}"
    )


def _telemetry_events(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    source_id = context["primary_source_idea_id"]
    events = [
        _event(
            "T1",
            "Workflow started",
            "activation",
            f"{context['target_user']} starts {context['workflow_context']}.",
            "Activation rate for the target workflow.",
            ["user_id", "account_id", "workflow_id", "started_at"],
            [context["target_user"], context["workflow_context"]],
            source_id,
        ),
        _event(
            "T2",
            "First value reached",
            "value",
            f"User completes {context['mvp_scope'][0]}.",
            _measurable_outcome(brief, context),
            ["user_id", "account_id", "scope_item", "completed_at"],
            context["mvp_scope"],
            source_id,
        ),
        _event(
            "T3",
            "Validation decision recorded",
            "validation",
            "Pilot, interview, or experiment evidence is accepted or rejected.",
            "Validated learning captured for the design brief.",
            ["decision_id", "evidence_type", "decision", "reviewer"],
            context["evidence"] or ["unknown validation evidence"],
            source_id,
        ),
        _event(
            "T4",
            "Guardrail triggered",
            "guardrail",
            "A known risk, quality issue, or support condition crosses threshold.",
            "Risk and reliability guardrail rate.",
            ["risk_id", "severity", "threshold", "triggered_at"],
            context["risks"] or ["unknown risk threshold"],
            source_id,
        ),
    ]
    text_blob = _text_blob(brief, context)
    if _contains(text_blob, ("integration", "api", "webhook", "sync")):
        events.append(
            _event(
                "T5",
                "Integration sync checked",
                "data_quality",
                "External integration payload is received, transformed, or rejected.",
                "Sync completeness and rejected payload rate.",
                ["integration_id", "payload_id", "status", "error_code"],
                ["integration or API dependency mentioned"],
                source_id,
            )
        )
    return events


def _event(
    event_id: str,
    name: str,
    category: str,
    trigger: str,
    metric_linkage: str,
    properties: list[str],
    evidence: list[str],
    source_id: str,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "name": name,
        "category": category,
        "trigger": trigger,
        "metric_linkage": metric_linkage,
        "required_properties": properties,
        "evidence": evidence,
        "source_idea_id": source_id,
    }


def _quality_risks(
    context: dict[str, Any], telemetry_events: list[dict[str, Any]]
) -> list[dict[str, str]]:
    risks = [
        {
            "id": "Q1",
            "name": "Ambiguous identity join",
            "severity": "medium",
            "description": "Events may not join cleanly across users, accounts, and workflow records.",
            "mitigation": "Require stable user_id, account_id, and workflow_id on every event.",
        },
        {
            "id": "Q2",
            "name": "Missing validation outcome",
            "severity": "high" if context["evidence_count"] == 0 else "medium",
            "description": "Telemetry can show activity without proving whether the design brief hypothesis worked.",
            "mitigation": "Record validation decision events with reviewer and evidence type.",
        },
    ]
    if any(event["category"] == "data_quality" for event in telemetry_events):
        risks.append(
            {
                "id": "Q3",
                "name": "Integration payload drift",
                "severity": "high",
                "description": "API or integration payload changes can create silent metric breaks.",
                "mitigation": "Track schema version, rejected payloads, and sync completeness.",
            }
        )
    if context["fallbacks_used"]:
        risks.append(
            {
                "id": "Q4",
                "name": "Sparse source context",
                "severity": "medium",
                "description": "Missing brief inputs force fallback event labels and open metric definitions.",
                "mitigation": "Resolve missing brief fields before launch acceptance.",
            }
        )
    return risks


def _instrumentation_gaps(
    context: dict[str, Any], brief: dict[str, Any], evidence_references: list[dict[str, str]]
) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    if "workflow_context" in context["fallbacks_used"]:
        gaps.append({"id": "missing_workflow_context", "description": "Workflow context is unknown; event triggers need product confirmation."})
    if "mvp_scope" in context["fallbacks_used"]:
        gaps.append({"id": "missing_mvp_scope", "description": "MVP scope is unknown; first-value event coverage is provisional."})
    if not _has_measurable_outcome(brief, context):
        gaps.append({"id": "missing_success_metric", "description": "Measurable outcome is missing; metric quality thresholds are open."})
    if context["evidence_count"] == 0:
        gaps.append({"id": "missing_evidence", "description": "No validation evidence or source idea evidence was found."})
    if not context["risks"]:
        gaps.append({"id": "missing_guardrail_thresholds", "description": "Risk thresholds are unknown; guardrail events need severity criteria."})
    return gaps


def _acceptance_checks(
    context: dict[str, Any],
    telemetry_events: list[dict[str, Any]],
    quality_risks: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        {
            "id": "A1",
            "name": "Event schema coverage",
            "check": f"{len(telemetry_events)} planned telemetry events have stable names, triggers, and required properties.",
            "owner": "Analytics owner",
        },
        {
            "id": "A2",
            "name": "Metric reconciliation",
            "check": "Activation, value, validation, and guardrail counts reconcile to source records for a seeded pilot account.",
            "owner": "Data owner",
        },
        {
            "id": "A3",
            "name": "Quality risk review",
            "check": f"{len(quality_risks)} telemetry quality risk(s) have named mitigations before launch.",
            "owner": context["buyer"],
        },
    ]


def _evidence_references(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for field in ("validation_plan", "synthesis_rationale"):
        value = text(brief.get(field))
        if value:
            references.append({"id": f"design_brief.{field}", "type": field, "description": value})
    for idea in context["source_ideas"]:
        if idea.get("missing"):
            continue
        for field in ("workflow_context", "validation_plan", "evidence_signals", "domain_risks"):
            values = list_values(idea.get(field))
            if values:
                references.append(
                    {
                        "id": f"{idea['id']}.{field}",
                        "type": field,
                        "description": join_text(values, ""),
                    }
                )
    return references


def _quality_posture(gaps: list[dict[str, str]], risks: list[dict[str, str]]) -> str:
    if gaps:
        return "instrumentation_discovery_required"
    if any(risk["severity"] == "high" for risk in risks):
        return "quality_risk_review_required"
    return "ready_for_telemetry_validation"


def _measurable_outcome(brief: dict[str, Any], context: dict[str, Any]) -> str:
    if text(brief.get("success_metric")):
        return text(brief.get("success_metric"))
    for value in [text(brief.get("validation_plan")), *context["evidence"]]:
        if any(ch.isdigit() for ch in value) or any(
            word in value.lower() for word in ("reconcile", "rate", "threshold", "measure")
        ):
            return value
    return "First-value completion rate."


def _has_measurable_outcome(brief: dict[str, Any], context: dict[str, Any]) -> bool:
    outcome = _measurable_outcome(brief, context)
    return outcome != "First-value completion rate."


def _text_blob(brief: dict[str, Any], context: dict[str, Any]) -> str:
    parts = [
        text(value)
        for value in brief.values()
        if isinstance(value, (str, int, float, list, dict))
    ]
    parts.extend(text(idea) for idea in context["source_ideas"])
    return " ".join(parts).lower()


def _contains(blob: str, terms: tuple[str, ...]) -> bool:
    return any(term in blob for term in terms)


def _filename_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in cleaned.split("-") if part) or "design-brief"
